#!/tests/pypy3-2.4.0-osx64/bin/pypy3
#! /usr/bin/env python3

# TODO:
#   * Check whether parsers other than VSFilter and libass accept "0" as colors in styles.
# To do in the longer term:
#   * Yugi comments are shown in the typical small windowed mode even when comments are hidden.
#     Check whether they're also shown in full-window mode.
#   * Check font size in VSFilter.
#       * Ugh, Windows uses bitmap fonts for MS PGothic.
#       * Welp, \fscx6400\fscy6400 looks ugly and has too low text width (sum of advances).
#   * English track.
#     Apologize for forgetting about Chinese (if there actually was a Chinese comment stream).
#   * Maybe figure out line height.
#     Remember that in ASS, line height is equal to \fs, which I forge to get 24pt nominal.
#       * Line height is 33px. (Line interval is 34px including 1px of hardcoded interline spacing.)
#         This matches the line height of Arial in Wordpad, but not in Notepad and not of MS PGothic.
#       * Ascender is 25px.
#         At least there's 25px from the top edge of the screen to the baseline of the topmost line.
#       * I think this should be used regardless of font.
#         Since I change the font explicitly in ASS, I'll need to work around the differing
#         metrics in different fonts by modifying the \move coordinates appropriately.
#   * Out of curiosity, check how NicoNico scales font size.
#   * Extensively check font fallback.
#   * Get MS PGothic from Windows 10.
# Epic fix for fonts:
#   * Generate a single font that contains exactly all glyphs necessary
#     for the comments as vectorized by GDI.
# Not applicable to this specific Japanese comment XML:
#   * Fix { ... } in comments, not just { ...
#   * Fix braces in yugi comments too.
# Figured out (I think) but impossible to replicate in ASS without manually vectorizing text:
#   * BevelFilter(distance: 1,
#                 angle: 45,
#                 highlightColor: 0x000000,
#                 highlightAlpha: 1,
#                 shadowColor: 0x000000,
#                 shadowAlpha: 1,
#                 blurX: 2,
#                 blurY: 2,
#                 strength: 1,
#                 quality: 1,
#                 type: "outer",
#                 knockout: false).
#     I still don't know what $strength does, but for $strength == 1:
#      1. Take the glyph outline and move it by $distance pixels up and to the left.
#      2. Take the glyph outline and move it by $distance pixels down and to the right.
#      3. Take the symmetric difference of these two outlines.
#           * More precisely, subtract each from the other, clip to some boundaries
#             halfway between the top-left and bottom-right corners or something,
#             and merge them into a single outline.
#           * Clipping aside, the "symmetric difference" simplification assumes
#             ($highlightColor, $highlightAlpha) == ($shadowColor, $shadowAlpha).
#      4. Rasterize this outline.
#      5. Blur the bitmap with a [1,1,1,...,1] kernel of length $blur if odd
#         or a [1,2,2,2,...,2,1] kernel of length ($blur+1) if $blur is even.
#           * Or possibly blur each of the two outline differences separately
#             and *then* clip.
#           * Order of horizontal/vertical and rounding has not been investigated.
#           * For $blurX = $blurY = 2, this is conveniently exactly \be1.
#         Repeat this step for a total of $quality times. (I think. Not tested.)
#      6. Inverse-clip the bitmap against the glyph outline.
#     For the heck of it, here's an attempt at doing it in my own New Subtitle Format:
#         \iclip(text)\be1\draw \pos(x-1,y-1){\text{text}} ^ \pos(x+1,y+1){\text{text}}
#     Hell, this is just turning into a plain-text syntax for SVG now!
#     Oh wow, turns out SVG doesn't even support this stuff!

import argparse, freetype, html, itertools, math, numbers, operator, os, pytz, random, re, sys
from collections import namedtuple, OrderedDict
from datetime import datetime
from decimal import Decimal
from html.parser import HTMLParser
from fractions import Fraction
from xml.etree import ElementTree

parser = argparse.ArgumentParser()
parser.add_argument('file', type=argparse.FileType('r'),
                    help='NicoNico comment XML file')
args = parser.parse_args()

unsupported = set()
unsupported_commands = set()

# This is the time the gate is opened
START_TIME = int(datetime(2016, 2, 11, 21, 50, tzinfo=pytz.timezone('Asia/Tokyo')).timestamp())
PASS = 2

assert PASS in {0, 1, 2}

# An unfair random number generator
def randint(a, b):
	return round(float(b - a) * random.random() + float(a))

def escape(text):
	# Break accidental escape sequences by inserting a zero-width space
	text = re.sub(r'\\([Nnh{}])', '\\\u200b\\1', text)
	# Preserve leading and trailing spaces
	# (let's hope the glyphs are the same!)
	text = re.sub(r'^ | $', r'\h', text)
	return text

class HTMLTranscoder(HTMLParser):
	def __init__(self):
		super().__init__(self, convert_charrefs=True)
		self.ass = []
	def _unsupported(self):
		if 'html' not in unsupported:
			print('This file contains HTML that I cannot handle. '
			      'It will be removed.',
			      file=sys.stderr)
			unsupported.add('html')
	def handle_starttag(self, tag, attrs):
		nattrs = len(attrs)
		attrs = dict(attrs)
		if len(attrs) != nattrs:
			# Repeated attribute names
			self._unsupported()
			attrs = {}
		if tag == 'br':
			# TOOD: apply \h
			#for i in range(len(self.ass) - 1, -1, -1):
			#	if 
			self.ass.append(r'\N')
			if attrs:
				self._unsupported()
		elif tag == 'b':
			self.ass.append(r'{\b1}')
			if attrs:
				self._unsupported()
		elif tag == 'i':
			self.ass.append(r'{\i1}')
			if attrs:
				self._unsupported()
		elif tag == 'u':
			self.ass.append(r'{\u1}')
			if attrs:
				self._unsupported()
		elif tag == 'a':
			if 'href' not in attrs:
				self._unsupported()
			else:
				self.handle_comment(attrs['href'])
				if attrs.keys() - {'href', 'target'}:
					self._unsupported()
		#elif tag == 'font':
		#	if 'face' in attrs:
		#		self.ass.append(r'{\fn%s}' % attrs[face])
		else:
			self._unsupported()
	def handle_endtag(self, tag):
		if tag == 'b':
			self.ass.append(r'{\b0}')
		elif tag == 'i':
			self.ass.append(r'{\i0}')
		elif tag == 'u':
			self.ass.append(r'{\u0}')
		elif tag == 'a':
			pass
		else:
			self._unsupported()
	def handle_data(self, data):
		self.ass.append(escape(data))
	def handle_comment(self, data):
		if '{' not in data and '}' not in data and '\\' not in data:
			self.ass += ['{', data, '}']
		else:
			# TODO: this needs some escaping
			self._unsupported()
	def handle_decl(self, decl):
		self._unsupported()
	def handle_pi(self, data):
		self._unsupported()
	def unknown_decl(self, data):
		self._unsupported()

def transcode_html(text):
	lines = text.split('<br>')
	if any('<' in line for line in lines):
		if 'html' not in unsupported:
			print('This file contains HTML that I cannot handle. '
			      'It will be left as is.',
			      file=sys.stderr)
			unsupported.add('html')
	return r'\N'.join(escape(html.unescape(line)) for line in lines)
	#transcoder = HTMLTranscoder()
	#transcoder.feed(text)
	#transcoder.close()
	#return ''.join(transcoder.ass)

def parse_args(string):
	for match in re.finditer(r'(?s)("(?:[^"\\]|\\.)*"?|[^ \t"](?:[^ \t\\]|\\.)*)', string):
		arg = match.group()
		if arg.startswith('"'):
			if re.match(r'(?s)"(?:[^"\\]|\\.)*"', arg):
				arg = arg[1:-1]
			else:
				arg = arg[1:]
				if not arg:
					continue
		arg = re.sub(r'(?s)\\(.)', r'\1', arg)
		yield arg

class Chat:
	_PREMIUM, _YUGI, _STAFF, _SEXINFO, _GENDER = 1, 2, 4, 8, 16
	_SIZES = {'small': 15, 'normal': 24, 'big': 39}
	_MAIL = {
		'small' : ('size'  , 'small' , False),
		'big'   : ('size'  , 'big'   , True ),
		'ue'    : ('valign', 'top'   , True ),
		'top'   : ('valign', 'top'   , True ),
		'shita' : ('valign', 'bottom', True ),
		'bottom': ('valign', 'bottom', True ),
		# NOTE: halign does not actually have any effect
		'migi'  : ('halign', 'right' , True ),
		'right' : ('halign', 'right' , True ),
		'hidari': ('halign', 'left'  , True ),
		'left'  : ('halign', 'left'  , True ),
		'hidden': ('hidden', True    , False),
		'se1'   : ('se'    , 1       , True ),
		'se2'   : ('se'    , 2       , True ),
		'184'   : ('iyayo' , True    , False),
	}
	_COLORS = {
		'white'         : (0xffffff, None),
		'red'           : (0xff0000, None),
		'green'         : (0x00ff00, None),
		'blue'          : (0x0000ff, None),
		'cyan'          : (0x00ffff, None),
		'yellow'        : (0xffff00, None),
		'purple'        : (0xc000ff, None),
		'pink'          : (0xff8080, None),
		'orange'        : (0xffc000, None),
		'niconicowhite' : (0xcccc99, 'premium'),
		'white2'        : (0xcccc99, 'premium'),
		'marineblue'    : (0x33fffc, 'premium'),
		'blue2'         : (0x33fffc, 'premium'),
		'madyellow'     : (0x999900, 'premium'),
		'yellow2'       : (0x999900, 'premium'),
		'passionorange' : (0xff6600, 'premium'),
		'orange2'       : (0xff6600, 'premium'),
		'nobleviolet'   : (0x6633cc, 'premium'),
		'purple2'       : (0x6633cc, 'premium'),
		'elementalgreen': (0x00cc66, 'premium'),
		'green2'        : (0x00cc66, 'premium'),
		'truered'       : (0xcc0033, 'premium'),
		'red2'          : (0xcc0033, 'premium'),
		'black'         : (0x000000, 'premium'),
		'fred'          : (0xbd0000, 'cyalume'),
		'fpink'         : (0xd300d3, 'cyalume'),
		'faqua'         : (0x00b1b1, 'cyalume'),
		'fblue'         : (0x0000d5, 'cyalume'),
		'fyellow'       : (0x999900, 'cyalume'),
		'fgreen'        : (0x007800, 'cyalume'),
		'forange'       : (0xff6600, 'cyalume'),
	}
	def __init__(self, text, *,
	             external_type=None, thread, vpos=None, date, date_usec='0',
	             mail=None, user_id, locale=None, no=None, premium='0',
	             anonymity=None, deleted=None, yourpost=None, score='0'):
		self.alpha = 1
		self.resume = False
		self.hidden = False
		self.text = text
		self.external_type = external_type
		self.thread = thread
		self.date = int(date) + int(date_usec) * Fraction('0.000001')
		# It's still not clear to me how exactly the date-based thing works,
		# but I think it has some random error such that trying to floor or
		# ceil or round or something will not be any more correct than this
		self.vpos = self.date - START_TIME
		if vpos is not None:
			self.vpos = max(self.vpos, int(vpos) * Fraction('0.01'))
		self.user_id = user_id
		self.locale = locale
		self.no = no
		self.anonymity = anonymity == '1'
		self.deleted = deleted == '1'
		self.yourpost = yourpost == '1'
		self.score = int(score)
		premium = int(premium)
		self.premium = bool(premium & self._PREMIUM)
		self.yugi = bool(premium & self._YUGI)
		self.staff = bool(premium & self._STAFF)
		if premium & self._SEXINFO:
			self.sex = 'f' if premium & self._GENDER else 'm'
		else:
			self.sex = None
		self.size = 'normal'
		self.valign = 'normal'
		self.halign = 'normal'
		self.color = 0xffffff
		self.iyayo = False
		self.se = None
		if mail is not None:
			for word in mail.split(' '):
				try:
					name, value, premium = self._MAIL[word]
				except KeyError:
					try:
						color, requirement = self._COLORS[word]
					except KeyError:
						pass
					else:
						if requirement == 'premium':
							allowed = self.premium or self.yugi
						elif requirement == 'cyalume':
							allowed = self.external_type == 'cyalume'
						elif requirement is None:
							allowed = True
						else:
							raise KeyError(requirement)
						if allowed:
							self.color = color
				else:
					if self.premium or not premium:
						setattr(self, name, value)
		assert self.iyayo == self.anonymity, \
			'presence of 184 does not match anonymity'
		if self.valign != 'normal':
			self.halign = 'normal'
		if self.external_type == 'cyalume':
			self.border_color = self.color
			self.color = 0xffffff
		else:
			self.border_color = 0x000000 if self.color else 0xffffff
		self.vstart = self.vpos
		if self.yugi:
			if not self.resume and ('se1' in mail or 'se2' in mail):
				if 'commands' not in unsupported:
					print('This file contains commands that I cannot handle.',
					      file=sys.stderr)
					unsupported.add('commands')
					unsupported_commands.add('se')
			if text.startswith('/'):
				self.command, *args = text[1:].split(' ')
				if self.command == 'perm':
					self.text = ' '.join(args)
					self.expire = 0
					self.priority = 0
				elif self.command in {'clear', 'cls'}:
					self.vend = self.vstart
				elif self.command == 'vote':
					# TODO: should this be None and checked for `is None`?
					self.text = ''
					self.expire = 0
					self.priority = 100
					self.mode = args.pop(0)
					args = parse_args(' '.join(args))
					if self.mode == 'start':
						self.text, *self.answers = args
						self.answers = list(map(escape, self.answers))
					elif self.mode == 'showresult':
						self.result_mode, *self.results = args
						self.results = list(map(int, self.results))
						if self.result_mode not in {'percent', 'per'}:
							if 'result_modes' not in unsupported:
								print('This file contains voting result modes '
								      'that I cannot handle. Result mode '
								      '"per" will be used instead.',
								      file=sys.stderr)
								unsupported.add('result_modes')
							self.result_mode = 'per'
							#text = []
							#for i, result in enumerate(self.results):
							#	if not i % 2 and i > 0:
							#		text.append('<br>')
							#	text.append()
							#	text.append('「' + questions + '」')
							#self.text = transcode_html(''.join(text))
				elif self.command in {'play', 'jump', 'redirect',
				                      'disconnect', 'hb'}:
					# Ignore
					raise NotImplementedError
				else:
					if 'commands' not in unsupported:
						print('This file contains commands '
						      'that I cannot handle.',
						      file=sys.stderr)
						unsupported.add('commands')
						unsupported_commands.add(self.command)
					raise NotImplementedError
			else:
				self.command = 'perm'
				self.expire = 15
				self.priority = 100 * self.hidden
				if not self.resume:
					# show
					pass
			if self.command in {'perm', 'vote'}:
				self.vend = self.vstart + self.expire
				self.text = transcode_html(self.text)
		else:
			self.command = None
			self.size = self._SIZES[self.size]
			self.vend = self.vstart + (5 if self.valign == 'normal' else 3)
			self.text = escape(self.text)
	def x(self, vpos):
		duration = float(self.vend - self.vstart)
		return WIDTH - (WIDTH + self.width) * float(vpos - self.vstart) / duration
	def random_y(self):
		return randint(0, HEIGHT - self.height)

chats = []
try:
	tree = ElementTree.parse(args.file)
	packet = tree.getroot()
	assert packet.tag == 'packet', 'the root element is not "packet"'
	for element in packet:
		assert element.tag == 'chat', \
			'the root element contains something other than "chat" elements'
		try:
			chats.append(Chat(element.text, **element.attrib))
		except NotImplementedError:
			pass
except (AssertionError, ElementTree.ParseError) as e:
	sys.exit('This is not a valid NicoNico comment XML file: ' + str(e))

chats.sort(key = lambda chat: chat.vstart)
max_vend = max(chat.vend for chat in chats)

# TODO: priorities
last = None
last_vote = None
for chat in chats:
	if chat.command == 'vote':
		if chat.mode == 'showresult':
			chat.answers = last_vote.answers
		if last_vote is not None:
			last_vote.vote_vend = min(last_vote.vote_vend, chat.vstart)
		if chat.mode == 'stop':
			if last is not None:
				last.vend = min(last.vend, chat.vstart)
				last = None
			last_vote = None
		else:
			chat.vote_vend = max_vend
			last_vote = chat
		if not chat.text:
			continue
	if chat.command in {'perm', 'vote'}:
		if last is not None:
			last.vend = min(last.vend, chat.vstart)
		if not chat.expire:
			chat.vend = max_vend
		last = chat
	elif chat.command in {'clear', 'cls'}:
		if last is not None:
			last.vend = min(last.vend, chat.vstart)
			last = None

if PASS <= 1:
	for chat in chats:
		if chat.command == 'vote' and chat.mode == 'stop':
			continue
		if chat.command in {None, 'perm', 'vote'}:
			chat.width, chat.height = Fraction('39'), Fraction('26.875')
		if chat.command == 'vote' and chat.mode != 'stop':
			chat.answer_sizes = [(Fraction('39'), Fraction('36'))
			                     for answer in chat.answers]
			if chat.mode == 'showresult':
				chat.percentage_sizes = chat.answer_sizes
else:
	with open('bounds.txt') as bounds:
		for chat in chats:
			if chat.command == 'vote' and chat.mode == 'stop':
				continue
			if chat.command == 'perm' or chat.command == 'vote' and chat.text:
				bounds.readline()
				bounds.readline()
			if (chat.command in {None, 'perm'} or
			    chat.command == 'vote' and chat.text):
				chat.width, chat.height = map(Fraction,
				                              bounds.readline().split()[1:])
			if chat.command == 'vote' and chat.mode != 'stop':
				chat.answer_sizes = []
				if chat.mode == 'showresult':
					chat.percentage_sizes = []
				for answer in chat.answers:
					bounds.readline()
					bounds.readline()
					chat.answer_sizes.append(tuple(map(Fraction,
						bounds.readline().split()[1:])))
					if chat.mode == 'showresult':
						chat.percentage_sizes.append(tuple(map(Fraction,
							bounds.readline().split()[1:])))

def time(s):
	cs = max(s, 0) * 100
	s, cs = divmod(cs, 100)
	m, s = divmod(s, 60)
	h, m = divmod(m, 60)
	return '%d:%02d:%02d.%02d' % (h, m, s, round(cs))

def color(color):
	return '&H%02X%02X%02X' % (color & 0xff, color >> 8 & 0xff, color >> 16)

def alpha(alpha):
	return '&H%02X' % round((1 - alpha) * 255)

def number(x):
	if int(x) == x:
		return str(int(x))
	if isinstance(x, Decimal):
		s = str(x)
	else:
		s = str(float(x))
	mant, *exp = s.lower().split('e', 1)
	if exp:
		exp = int(exp[0])
	if not exp:
		return mant.rstrip('0')
	i, *f = mant.split('.', 1)
	f = f[0] if f else ''
	if exp >= len(f):
		return i + f + '0' * (exp - len(f))
	elif exp > 0:
		return i + f[:exp] + '.' + f[exp:]
	elif exp > -len(i):
		return i[:exp] + '.' + i[exp:] + f.rstrip('0')
	else:
		return '0.' + '0' * (-exp - len(i)) + i + f.rstrip('0')

Point = namedtuple('Point', ('x', 'y'))

class Rectangle:
	__slots__ = '_left', '_top', '_width', '_height'
	def __new__(cls, x, y, w, h):
		obj = super().__new__(cls)
		obj._left = x
		obj._top = y
		obj._width = w
		obj._height = h
		return obj
	@property
	def width(self):
		return self._width
	@property
	def height(self):
		return self._height
	@property
	def left(self):
		return self._left
	@property
	def top(self):
		return self._top
	@property
	def right(self):
		return self._left + self._width
	@property
	def bottom(self):
		return self._top + self._height
	@property
	def center(self):
		return Point(self._left + self._width / 2,
		             self._top + self._height / 2)

def answer_box(i, n):
	assert 2 <= n <= 9, 'invalid number of answers in a vote command'
	spacing = 6
	columns = 3 - (n in {2, 4})
	rows = 3 - (n < 7)
	x_offset = (columns - n % columns) / 2 * (i >= n - n % columns)
	y_offset = 0.5 * (n < 4)
	width = Fraction(WIDTH - spacing * (columns + 1), columns)
	height = Fraction(HEIGHT - spacing * (rows + 1), rows)
	x = i % columns + x_offset
	y = i // columns + y_offset
	x = spacing * (x + 1) + width * x
	y = spacing * (y + 1) + height * y
	return Rectangle(x, y, width, height)

#try:
#	log2 = math.log2
#except AttributeError:
#	log2 = lambda x: math.log(x, 2)

class Drawing:
	__slots__ = '_commands', '_p'
	@classmethod
	def _from_commands(cls, commands):
		obj = super().__new__(cls)
		obj._commands = commands
		obj._p = None
		for contour in commands:
			if contour[-1] == ('l', contour[0][1], contour[0][2]):
				contour.pop()
		return obj
	def __new__(cls, words):
		if isinstance(words, str):
			words = words.split()
			for i in range(len(words)):
				try:
					words[i] = Fraction(Decimal(words[i]))
				except Exception:
					pass
		commands = []
		contour = []
		mode = None
		arg = None
		had_commands = True
		for word in itertools.chain(words, ('m',)):
			if isinstance(word, (numbers.Real, Decimal)):
				if mode is None:
					raise ValueError('missing initial mode in drawing')
				if arg is None:
					arg = word
				else:
					if mode == 'm' and had_commands:
						raise ValueError('empty contour in drawing')
					contour.append((mode, arg, word))
					arg = None
					had_commands = True
			elif isinstance(word, str):
				if mode is None and word != 'm':
					raise ValueError('initial mode in drawing is not "m"')
				if arg is not None:
					raise ValueError('extraneous number in drawing')
				if not had_commands:
					raise ValueError('not enough numbers in drawing')
				if mode == 'm' == word:
					raise ValueError('empty contour in drawing')
				if word == 'm' and contour:
					commands.append(contour)
					contour = []
				mode = word
				had_commands = False
			else:
				raise TypeError('drawing elements must be real numbers or '
				                "strings, not '%s'" % type(word).__name__)
		if not commands:
			raise ValueError('empty drawing')
		return cls._from_commands(commands)
	@staticmethod
	def _p_upper_bound(number):
		#number = abs(number)
		#return min(math.ceil(log2((1 << Drawing.MAX_P) / number)),
		#           Drawing.MAX_P)
		shift = 0
		while shift < 31:
			if not -1 << 25 <= round(number * (1 << shift)) < 1 << 25:
				break
			shift += 1
		if not shift:
			raise ValueError('coordinate too large in drawing')
		return shift
	@staticmethod
	def _p_lower_bound(number, p):
		#number = abs(number)
		#shift = 0
		#while shift < Drawing.MAX_P:
		#	x = number * (1 << shift)
		#	shift += 1
		#	if int(x) == x:
		#		break
		#return shift
		x = round(number * (1 << p - 1))
		if not x:
			return 1
		while not x & 1:
			x >>= 1
			p -= 1
		return p
	@property
	def p(self):
		if self._p is not None:
			return self._p
		p = min(min(self._p_upper_bound(x),
		            self._p_upper_bound(y)) for contour in self._commands
		                                    for m, x, y in contour)
		p = max(max(self._p_lower_bound(x, p),
		            self._p_lower_bound(y, p)) for contour in self._commands
		                                       for m, x, y in contour)
		self._p = p
		return p
	def __str__(self):
		words = []
		mode = None
		shift = self.p - 1
		for contour in self._commands:
			for m, x, y in contour:
				if m != mode:
					words.append(m)
					mode = m
				words.append(str(round(x * (1 << shift))))
				words.append(str(round(y * (1 << shift))))
		return ' '.join(words)
	def __repr__(self):
		words = []
		mode = None
		for contour in self._commands:
			for m, x, y in contour:
				if m != mode:
					words.append(m)
					mode = m
				words.append(x)
				words.append(y)
		return 'Drawing(%r)' % words
	def __reversed__(self):
		commands = []
		for contour in self._commands:
			mode = 'm'
			reversed_contour = []
			for m, x, y in contour[::-1]:
				reversed_contour.append((mode, x, y))
				mode = m
			commands.append(reversed_contour)
		return self._from_commands(commands)
	def __add__(self, vector):
		if not isinstance(vector, tuple):
			raise NotImplemented
		dx, dy = vector
		commands = [[(m, x + dx, y + dy) for m, x, y in contour]
		                                 for contour in self._commands]
		return self._from_commands(commands)
	def __mul__(self, other):
		if not isinstance(other, (numbers.Real, Decimal)):
			return NotImplemented
		commands = [[(m, x * other, y * other) for m, x, y in contour]
		                                       for contour in self._commands]
		return self._from_commands(commands)
	def __xor__(self, other):
		if not isinstance(other, Drawing):
			return NotImplemented
		return self._from_commands(self._commands + reversed(other)._commands)

_PyHASH_MODULUS = sys.hash_info.modulus

# Does sqrt(2) exist modulo _PyHASH_MODULUS?
# It exists iff _PyHASH_MODULUS & 7 in {1, 7},
# but it's hard to find if it's 1, so don't bother.
if _PyHASH_MODULUS & 7 == 7:
	_PyHASH_SQRT2 = pow(2, _PyHASH_MODULUS + 1 >> 2, _PyHASH_MODULUS)
else:
	_PyHASH_SQRT2 = None

class TransformedSqrt2(numbers.Real):
	__slots__ = 'coef', 'offset'
	def __new__(cls, coef, offset):
		if not isinstance(coef, numbers.Rational):
			raise TypeError("coef must be a rational number")
		if not isinstance(offset, numbers.Rational):
			raise TypeError("offset must be a rational number")
		obj = super().__new__(cls)
		obj.coef = Fraction(coef)
		obj.offset = Fraction(offset)
		return obj
	def __abs__(self):
		return -self if self < 0 else +self
	def __add__(self, other):
		if isinstance(other, TransformedSqrt2):
			return TransformedSqrt2(self.coef + other.coef,
			                        self.offset + other.offset)
		if isinstance(other, numbers.Rational):
			return TransformedSqrt2(self.coef, self.offset + other)
		if isinstance(other, float):
			return float(self) + other
		if isinstance(other, complex):
			return complex(self) + other
		return NotImplemented
	def __bool__(self):
		return bool(self.coef and self.offset)
	def __ceil__(self):
		return self._newton(math.ceil)
	def __copy__(self):
		if type(self) is TransformedSqrt2:
			return self
		return type(self)(self.coef, self.offset)
	def __deepcopy__(self):
		if type(self) is TransformedSqrt2:
			return self
		return type(self)(self.coef, self.offset)
	def __divmod__(self, other):
		if isinstance(other, (TransformedSqrt2, numbers.Rational)):
			div = math.floor(self / other)
			return div, self - div * other
		if isinstance(other, float):
			return divmod(float(self), other)
		if isinstance(other, complex):
			return divmod(complex(self), other)
		return NotImplemented
	def __eq__(self, other):
		if isinstance(other, TransformedSqrt2):
			return (self.coef, self.offset) == (other.coef, other.offset)
		if isinstance(other, numbers.Complex) and not other.imag:
			other = other.real
		if isinstance(other, (numbers.Rational, float, Decimal)):
			return not self.coef and self.offset == other
		return NotImplemented
	def __float__(self):
		return self._newton(float)
	def __floor__(self):
		return self._newton(math.floor)
	def __floordiv__(self, other):
		if isinstance(other, (TransformedSqrt2, numbers.Rational)):
			return math.floor(self / other)
		if isinstance(other, float):
			return float(self) // other
		if isinstance(other, complex):
			return complex(self) // other
		return NotImplemented
	def __ge__(self, other):
		return self._richcmp(other, operator.ge)
	def __gt__(self, other):
		return self._richcmp(other, operator.gt)
	def __hash__(self):
		if _PyHASH_SQRT2 is not None:
			return hash(self.coef * _PyHASH_SQRT2 + self.offset)
		# Just pretend we're a complex number
		hash_ = hash(self.coef) * sys.hash_info.imag + hash(self.offset)
		sign_bit = 1 << sys.hash_info.width - 1
		hash_ = (hash_ & sign_bit - 1) - (hash_ & sign_bit)
		return -2 if hash_ == -1 else hash_
	def __le__(self, other):
		return self._richcmp(other, operator.le)
	def __lt__(self, other):
		return self._richcmp(other, operator.lt)
	def __mod__(self, other):
		if isinstance(other, (TransformedSqrt2, numbers.Rational)):
			return self - math.floor(self / other) * other
		if isinstance(other, float):
			return float(self) % other
		if isinstance(other, complex):
			return complex(self) % other
		return NotImplemented
	def __mul__(self, other):
		if isinstance(other, TransformedSqrt2):
			coef = self.offset * other.coef + self.coef * other.offset
			offset = 2 * self.coef * other.coef + self.offset * other.offset
			return TransformedSqrt2(coef, offset)
		if isinstance(other, numbers.Rational):
			return TransformedSqrt2(self.coef * other, self.offset * other)
		if isinstance(other, float):
			return float(self) * other
		if isinstance(other, complex):
			return complex(self) * other
		return NotImplemented
	def __neg__(self):
		return TransformedSqrt2(-self.coef, -self.offset)
	def _newton(self, round):
		"""X.newton(round)

Find round(X.coef * sqrt(2) + X.offset) using the Newton-Raphson method."""
		a, b = self.coef, self.offset
		if not a:
			return round(b)
		l, r = a, 2 * a
		aa2 = r * a
		while True:
			rl = round(l + b)
			if rl == round(r + b):
				return rl
			r = (l + r) / 2
			l = aa2 / r
	def __pos__(self):
		return TransformedSqrt2(self.coef, self.offset)
	def __pow__(self, other):
		if isinstance(other, numbers.Rational) and other.denominator == 1:
			power = other.numerator
			reciprocal = power < 0
			if reciprocal:
				power = -power
			x, r = self, self if power & 1 else TransformedSqrt2(0, 1)
			power >>= 1
			while power:
				x *= x
				if power & 1:
					r *= x
				power >>= 1
			return 1 / r if reciprocal else r
		return float(self) ** other
	def __radd__(self, other):
		if isinstance(other, TransformedSqrt2):
			return TransformedSqrt2(other.coef + self.coef,
			                        other.offset + self.offset)
		if isinstance(other, numbers.Rational):
			return TransformedSqrt2(self.coef, other + self.offset)
		if isinstance(other, numbers.Real):
			return float(other) + float(self)
		if isinstance(other, numbers.Complex):
			return complex(other) + complex(self)
		return NotImplemented
	def __rdivmod__(self, other):
		if isinstance(other, (TransformedSqrt2, numbers.Rational)):
			div = math.floor(other / self)
			return div, other - div * self
		if isinstance(other, numbers.Real):
			return divmod(float(other), float(self))
		if isinstance(other, numbers.Complex):
			return divmod(complex(other), complex(self))
		return NotImplemented
	def __reduce__(self):
		return type(self), (self.coef, self.offset)
	def __repr__(self):
		return 'TransformedSqrt2(%r, %r)' % (self.coef, self.offset)
	def __rfloordiv__(self, other):
		if isinstance(other, (TransformedSqrt2, numbers.Rational)):
			return math.floor(other / self)
		if isinstance(other, numbers.Real):
			return float(other) // float(self)
		if isinstance(other, numbers.Complex):
			return complex(other) // complex(self)
		return NotImplemented
	def _richcmp(self, other, op):
		# (a - c) * sqrt(2) op d - b
		# where a, b, c, d = self.coef, self.offset, other.coef, other.offset
		if isinstance(other, TransformedSqrt2):
			lhs = self.coef - other.coef
			rhs = other.offset - self.offset
		elif isinstance(other, (numbers.Rational, float, Decimal)):
			try:
				other = Fraction(other)
			except (OverflowError, ValueError):
				# other is infinite or NaN. Use the type's usual rules.
				# Exact finite values don't matter, so just
				# drop in arbitrary ints to avoid type errors.
				# Preserve signs where appropriate.
				lhs, rhs = self.coef.numerator, other
			else:
				lhs, rhs = self.coef, other - self.offset
		else:
			return NotImplemented
		lhs_sign = (lhs > 0) - (lhs < 0)
		rhs_sign = (rhs > 0) - (rhs < 0)
		if lhs_sign != rhs_sign:
			return op(lhs_sign, rhs_sign)
		elif lhs_sign >= 0:
			return op(2 * lhs * lhs, rhs * rhs)
		else:
			return op(rhs * rhs, 2 * lhs * lhs)
	def __rmod__(self, other):
		if isinstance(other, (TransformedSqrt2, numbers.Rational)):
			return other - math.floor(other / self) * self
		if isinstance(other, numbers.Real):
			return float(other) % float(self)
		if isinstance(other, numbers.Complex):
			return complex(other) % complex(self)
		return NotImplemented
	def __rmul__(self, other):
		if isinstance(other, TransformedSqrt2):
			coef = other.offset * self.coef + other.coef * self.offset
			offset = 2 * other.coef * self.coef + other.offset * self.offset
			return TransformedSqrt2(coef, offset)
		if isinstance(other, numbers.Rational):
			return TransformedSqrt2(other * self.coef, other * self.offset)
		if isinstance(other, numbers.Real):
			return float(other) * float(self)
		if isinstance(other, numbers.Complex):
			return complex(other) * complex(self)
		return NotImplemented
	def __round__(self):
		return self._newton(round)
	def __rpow__(self, other):
		if not self.coef:
			return other ** self.offset
		return other ** float(self)
	def __rtruediv__(self, other):
		if isinstance(other, TransformedSqrt2):
			coef = other.offset * self.coef - other.coef * self.offset
			offset = 2 * self.coef * other.coef - self.offset * other.offset
			divisor = 2 * self.coef * self.coef - self.offset * self.offset
			return TransformedSqrt2(coef / divisor, offset / divisor)
		if isinstance(other, numbers.Rational):
			coef = other * self.coef
			offset = -self.offset * other
			divisor = 2 * self.coef * self.coef - self.offset * self.offset
			return TransformedSqrt2(coef / divisor, offset / divisor)
		if isinstance(other, numbers.Real):
			return float(other) / float(self)
		if isinstance(other, numbers.Complex):
			return complex(other) / complex(self)
		return NotImplemented
	def __str__(self):
		if not self.coef:
			return str(self.offset)
		coef = '%s' if self.coef.denominator == 1 else '(%s)'
		if not self.offset:
			return '%s*sqrt(2)' % coef % self.coef
		offset = '%s' if self.offset.numerator < 0 else '+%s'
		return '%s*sqrt(2)%s' % (coef, offset) % (self.coef, self.offset)
	def __truediv__(self, other):
		if isinstance(other, TransformedSqrt2):
			coef = self.offset * other.coef - self.coef * other.offset
			offset = 2 * other.coef * self.coef - other.offset * self.offset
			divisor = 2 * other.coef * other.coef - other.offset * other.offset
			return TransformedSqrt2(coef / divisor, offset / divisor)
		if isinstance(other, numbers.Rational):
			return TransformedSqrt2(self.coef / other, self.offset / other)
		if isinstance(other, float):
			return float(self) / other
		if isinstance(other, complex):
			return complex(self) / other
		return NotImplemented
	def __trunc__(self):
		return self._newton(math.trunc)

def rounded_box(width, height, radius):
	w = width
	h = height
	r = radius
	# bezier_offset = radius * 4 * (sqrt(2) - 1) / 3
	# o = radius - bezier_offset = radius * (7 - 4 * sqrt(2)) / 3
	o = radius * TransformedSqrt2(Fraction(-4, 3), Fraction(7, 3))
	return Drawing(('m',  w-r,  0 ,  'b',  w-o,   0 ,   w ,  o ,   w ,  r ,
	                'l',   w , h-r,  'b',   w ,  h-o,  w-o,  h ,  w-r,  h ,
	                'l',   r ,  h ,  'b',   o ,   h ,   0 , h-o,   0 , h-r,
	                'l',   0 ,  r ,  'b',   0 ,   o ,   o ,  0 ,   r ,  0 ))

class SegmentTree:
	__slots__ = '_vstart', '_vend', '_chats', '_leaf', '_left', '_right'
	def __init__(self, vstart, vend):
		self._vstart = vstart
		self._vend = vend
		self._chats = set()
		self._leaf = vend - vstart == 1
		if not self._leaf:
			vmiddle = vstart + vend >> 1
			self._left = SegmentTree(vstart, vmiddle)
			self._right = SegmentTree(vmiddle, vend)
	def add(self, chat):
		if chat.vstart >= self._vend or chat.vend <= self._vstart:
			return
		elif (self._leaf or
		      chat.vstart <= self._vstart and chat.vend >= self._vend):
			self._chats.add(chat)
		else:
			self._left.add(chat)
			self._right.add(chat)
	def __getitem__(self, vpos):
		if not self._vstart <= vpos < self._vend:
			return frozenset()
		if self._leaf:
			return frozenset(self._chats)
		return self._left[vpos] | self._right[vpos] | self._chats

# Niconico player (Flash) metrics (based on GDI in some way)
LINE_HEIGHT = {15: 22, 24: 33, 39: 49}
ASCENDER = {15: 16, 24: 25, 39: 38}

# VSFilter metrics (GDI with fs*=64 and then lround(asc,desc/=8))
FONTS = OrderedDict((
	('Arial', ('a', freetype.Face('ARIALBD.TTF'),
	           {24: {'fs': 27, 'asc': Fraction(175, 8), 'desc': Fraction(41, 8)},
	            15: {'fs': 17, 'asc': Fraction(110, 8), 'desc': Fraction(26, 8)},
	            39: {'fs': 44, 'asc': Fraction(285, 8), 'desc': Fraction(67, 8)}})),
	('MS PGothic', ('g', freetype.Face('/Library/Fonts/Microsoft/MS PGothic.ttf'),
	                {24: {'fs': 24, 'asc': Fraction(165, 8), 'desc': Fraction(27, 8)},
	                 15: {'fs': 15, 'asc': Fraction(103, 8), 'desc': Fraction(17, 8)},
	                 39: {'fs': 39, 'asc': Fraction(268, 8), 'desc': Fraction(44, 8)}})),
	('Segoe UI Symbol', (None, freetype.Face('SEGUISYM.TTF'),
	                     {24: {'fs': 32, 'asc': Fraction(208, 8), 'desc': Fraction(48, 8)}})),
	('Nirmala UI', (None, freetype.Face('NIRMALAB.TTF'),
	                {24: {'fs': 32, 'asc': Fraction(208, 8), 'desc': Fraction(49, 8)}})),
))

SIZE = 24
COLOR = 0xffffff
BORDER_COLOR = 0x000000
WIDTH = 672
HEIGHT = 378
DANMAKU_ALPHA = Fraction('0.6')
QUESTION_HORIZONTAL_PADDING = 6
QUESTION_MIN_SIZE = 24
QUESTION_MAX_SIZE = 36
QUESTION_SIZE = QUESTION_MAX_SIZE if PASS <= 1 else QUESTION_MIN_SIZE * Fraction(2, 3)
YUGI_SCALE = 100 if PASS <= 1 else 99

print('''[Script Info]
ScriptType: v4.00+
Language: ja
LayoutResX: {WIDTH}
LayoutResY: {HEIGHT}
PlayResX: {PLAY_RES_X}
PlayResY: {PLAY_RES_Y}
ScaledBorderAndShadow: yes
YCbCr Matrix: TV.709
WrapStyle: 2

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: a,Arial,{ARIAL_SIZE},&H00FFFFFF,0,&H77000000,0,-1,0,0,0,100,100,0,0,1,13,0,8,0,0,0,1
Style: g,MS PGothic,{MS_PGOTHIC_SIZE},&H00FFFFFF,0,&H77000000,0,-1,0,0,0,100,100,0,0,1,13,0,8,0,0,0,1
Style: v,MS PGothic,{QUESTION_SIZE},&H4DFFFFFF,0,&HA0000000,0,0,0,0,0,100,100,0,0,1,13,0,5,0,0,0,1
Style: p,MS PGothic,{MS_PGOTHIC_SIZE},&H4D00FFFF,0,&HA0000000,0,0,0,0,0,100,100,0,0,1,13,0,2,0,0,0,1
Style: y,MS PGothic,{MS_PGOTHIC_SIZE},&H66FFFFFF,0,0,0,0,0,0,0,{YUGI_SCALE},{YUGI_SCALE},0,0,1,0,0,4,0,0,0,1
Style: r,,0,&H4DD89485,0,0,0,0,0,0,0,100,100,0,0,1,0,0,5,0,0,0,1
Style: l,,0,&H4DFFFFFF,0,0,0,0,0,0,0,100,100,0,0,1,0,0,5,0,0,0,1
Style: b,,0,&H66000000,0,0,0,0,0,0,0,100,100,0,0,1,0,0,5,0,0,0,1
Style: m,,0,&H66000000,0,&H66373737,0,0,0,0,0,100,100,0,0,1,14,0,5,0,0,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text'''
.format(WIDTH = WIDTH,
        HEIGHT = HEIGHT,
        PLAY_RES_X = WIDTH * 13,
        PLAY_RES_Y = HEIGHT * 13,
        ARIAL_SIZE = number(FONTS['Arial'][2][SIZE]['fs'] * 13),
        MS_PGOTHIC_SIZE = number(FONTS['MS PGothic'][2][SIZE]['fs'] * 13),
        QUESTION_SIZE = number(QUESTION_SIZE * 13),
        YUGI_SCALE = number(YUGI_SCALE)))

chars = {name: set() for name in FONTS}

tree = SegmentTree(math.floor(min(chat.vstart for chat in chats)),
                   math.ceil(max(chat.vend for chat in chats)))
for chat in chats:
	if chat.command in {'perm', 'vote'}:
		if PASS <= 1:
			chat.vstart, chat.vend = 0, 10
		if chat.command == 'perm' or chat.text:
			chars['MS PGothic'].update(chat.text.replace(r'\N', '').replace(r'\h', '\xa0'))
			# FIXME: go from hardcoded sizes and coordinates to honoring WIDTH and HEIGHT
			print(r'Dialogue: 2,%s,%s,b,,0,0,0,,{\pos(4368,364)\p1}m 0 0 l 8736 0 8736 728 0 728' %
			      (time(chat.vstart), time(chat.vend)))
			# print(r'Dialogue: 2,%s,%s,m,,0,0,0,,{\pos(336,28)\p21}m 0 0 l 1405091840 0 1405091840 112923569 0 112923569' %
			print(r'Dialogue: 2,%s,%s,m,,0,0,0,,{\pos(4368,364)\p1}m 0 0 l 8710 0 8710 700 0 700' %
			      (time(chat.vstart), time(chat.vend)))
			scale = min(672 / chat.width, 56 / chat.height, 1) - Fraction('0.01')
			override = r'\pos(%s,364)' % number((672 - chat.width * scale) * 13 / 2)
			if scale != Fraction('0.99'):
				override += r'\fscx{0}\fscy{0}'.format(number(scale * 100))
			print(r'Dialogue: 2,%s,%s,y,,0,0,0,,{%s}%s' %
			      (time(chat.vstart), time(chat.vend), override, chat.text))
		if chat.command == 'vote':
			if chat.mode != 'stop':
				if PASS <= 1:
					chat.vote_vend = 10
				for i, answer in enumerate(chat.answers):
					box = answer_box(i, len(chat.answers))
					text = '%d:%s' % (i + 1, answer)
					thickness = max(box.width * Fraction('0.015'), 2)
					radius = box.width * Fraction('0.15') / 2
					outer = rounded_box(box.width, box.height,
					                    radius + thickness / 2)
					middle = rounded_box(box.width - thickness,
					                     box.height - thickness,
					                     radius)
					inner = rounded_box(box.width - thickness * 2,
					                    box.height - thickness * 2,
					                    radius - thickness / 2)
					outline = outer ^ (inner + (thickness, thickness))
					middle *= 13
					outline *= 13
					print(r'Dialogue: 1,%s,%s,r,,0,0,0,,{\pos(%s,%s)\p%d}%s' %
					      (time(chat.vstart), time(chat.vote_vend),
					       number(box.center.x * 13),
					       number(box.center.y * 13),
					       middle.p, middle))
					print(r'Dialogue: 1,%s,%s,l,,0,0,0,,{\pos(%s,%s)\p%d}%s' %
					      (time(chat.vstart), time(chat.vote_vend),
					       number(box.center.x * 13),
					       number(box.center.y * 13),
					       outline.p, outline))
					y, percentage = box.center.y, None
					if (chat.mode == 'showresult' and
					    chat.result_mode in {'percent', 'per'}):
						total = sum(chat.results)
						if total:
							percentage = '%.1f%%' % round(chat.results[i] * 100 / total, 1)
							y -= Fraction(chat.percentage_sizes[i][1], 2)
					# TODO: line wrapping
					#scale = min((box.width - QUESTION_HORIZONTAL_PADDING * 2) / chat.answer_sizes[i][0], 1)
					#override = r'\fscx{0}\fscy{0}'.format(number(scale * 100))
					override = ''
					if PASS == 2:
						box_width = box.width - QUESTION_HORIZONTAL_PADDING * 2
						text_width = min(chat.answer_sizes[i][0], box_width)
						columns = 3 - (len(chat.answers) in {2, 4})
						size = (QUESTION_MIN_SIZE +
						        (QUESTION_MAX_SIZE - QUESTION_MIN_SIZE) *
						        min((box_width - text_width) * 2 / box_width,
						            1)) * Fraction(2, columns)
						if size != QUESTION_SIZE:
							override = r'\fs%s' % number(size * 13)
					chars['MS PGothic'].update(text.replace(r'\N', '').replace(r'\h', '\xa0'))
					print(r'Dialogue: 1,%s,%s,v,,0,0,0,,{\pos(%s,%s)%s}%s' %
					      (time(chat.vstart), time(chat.vote_vend),
					       number(box.center.x * 13), number(y * 13),
					       override, text))
					if percentage is not None:
						override = ''
						if PASS == 2:
							scale = box.width / chat.percentage_sizes[i][0]
							if scale < 1:
								override = r'\fscx{0}\fscy{0}'
								override = override.format(number(scale * 100))
						chars['MS PGothic'].update(percentage.replace(r'\N', '').replace(r'\h', '\xa0'))
						print(r'Dialogue: 1,%s,%s,p,,0,0,0,,{\pos(%s,%s)%s}%s' %
						      (time(chat.vstart), time(chat.vote_vend),
						       number(box.center.x * 13),
						       number((box.bottom - 6) * 13),
						       override, percentage))
		continue
	
	if chat.command is not None:
		continue
	
	overrides = []
	
	if chat.color != COLOR:
		overrides.append(r'\c%s' % color(chat.color))
	
	if chat.border_color != BORDER_COLOR:
		overrides.append(r'\3c%s' % color(chat.border_color))
	
	font = None
	size = None
	text = []
	braces = problematic_braces = False
	ascender = 0
	for c in chat.text:
		# Variation Selectors block
		if 0xFE00 <= ord(c) <= 0xFE0F:
			if font is None:
				if 'lone' not in unsupported:
					print('This file contains lone characters without '
					      'glyphs. Arial will be used at your peril.',
					      file=sys.stderr)
					# Not sure things like the ascender calculation
					# will be correct either...
					unsupported.add('lone')
				font_name = 'Arial'
		elif c == '\u263A':  # WHITE SMILING FACE
			if font is not None and font_name == 'MS PGothic':
				# WTF, Windows
				pass
			else:
				font_name = 'Arial'
		else:
			for font_name, (style, extra_font, sizes) in FONTS.items():
				if extra_font.get_char_index(c):
					chars[font_name].add(c)
					break
			else:
				if 'fonts' not in unsupported:
					print('This file contains characters not in any '
					      'known font. Arial will be used at your peril.',
					      file=sys.stderr)
					unsupported.add('fonts')
				font_name = 'Arial'
		style, extra_font, sizes = FONTS[font_name]
		if font is not extra_font:
			if style is not None:
				override = r'\r' + style
				size = SIZE
			else:
				override = r'\fn' + font_name
			if sizes[chat.size]['fs'] != size:
				override += r'\fs%s' % number(sizes[chat.size]['fs'] * 13)
			size = sizes[chat.size]['fs']
			if text and text[-1] == '\\':
				text.append('\u200b')
			text.append('{%s}' % override)
			problematic_braces |= braces
			font = extra_font
		if c == '{':
			braces = True
		text.append(c)
		ascender = max(ascender, sizes[chat.size]['asc'])
	if PASS == 0:
		continue
	if problematic_braces:
		if 'braces' not in unsupported:
			print('This file contains "{" in comments before font '
			      'changes. They will appear as "\\" in VSFilter.',
			      file=sys.stderr)
			unsupported.add('braces')
		for i in range(len(text) - 1, -1, -1):
			if len(text[i]) > 1:
				break
		for i in range(i - 1, -1, -1):
			if text[i] == '{':
				text[i] = r'\{{}'
	
	chat.height = LINE_HEIGHT[chat.size]
	if chat.valign == 'bottom':
		chat.y = HEIGHT - chat.height
	else:
		chat.y = 0
	if PASS != 1:
		overflow = False
		changed = True
		previous_chats = set()
		for vpos in range(math.floor(chat.vstart), math.ceil(chat.vend)):
			previous_chats |= tree[vpos]
		while changed:
			changed = False
			for previous_chat in previous_chats:
				if (chat.valign == 'normal') != (previous_chat.valign == 'normal'):
					continue
				if not (chat.y + chat.height > previous_chat.y and
				        previous_chat.y + previous_chat.height > chat.y):
					continue
				vstart = max(chat.vstart, previous_chat.vstart)
				vend = min(chat.vend, previous_chat.vend)
				if vstart >= vend:
					continue
				xstart = chat.x(vstart)
				xend = chat.x(vend)
				previous_xstart = previous_chat.x(vstart)
				previous_xend = previous_chat.x(vend)
				if not ((xstart + chat.width > previous_xstart and
				         previous_xstart + previous_chat.width > xstart) or
				        (xend + chat.width > previous_xend and
				         previous_xend + previous_chat.width > xend)):
					continue
				if chat.valign == 'bottom':
					chat.y = previous_chat.y - chat.height - 1
				else:
					chat.y = previous_chat.y + previous_chat.height + 1
				if chat.y + chat.height > HEIGHT:
					overflow = True
					break
				changed = True
				break
		if overflow:
			chat.alpha = DANMAKU_ALPHA
			chat.y = chat.random_y()
		tree.add(chat)
	# Place the baseline where it should be
	y = chat.y + ASCENDER[chat.size] - ascender
	if chat.valign == 'normal':
		# VSFilter places the event at trunc(pos)-ceil(width/2),
		# where all rounding is done to the nearest 1/8 layout pixel.
		# For the left-hand position, this works out to 0 as is; perfect!
		# For the right-hand position, we need to ceil the position
		# we give it to ensure the result is not below WIDTH.
		# As for non-VSFilter, this should at least do no harm.
		overrides.append(r'\move(%s,%s,%s,%s)' %
		                 (number((WIDTH + Fraction(math.ceil(chat.width * 4), 8)) * 13),
		                  number(y * 13),
		                  number(-chat.width * 13 / 2),
		                  number(y * 13)))
	else:
		overrides.append(r'\pos(%s,%s)' %
		                 (number(WIDTH * 13 / 2), number(y * 13)))
	
	if chat.alpha * 510 < 509:
		overrides.append(r'\alpha%s' % alpha(chat.alpha))
	
	savings = {'a': 0, 'g': 0}
	for term in text:
		if term.startswith(r'{\r'):
			savings[term[3]] += 1
	if text[0].startswith(r'{\r'):
		savings[text[0][3]] += 2
	style = max(savings, key=savings.__getitem__)
	for i in range(len(text)):
		if text[i].startswith(r'{\r' + style):
			text[i] = r'{\r' + text[i][4:]
	if re.match(r'^\{\\r(?![ag])', text[0]):
		text[0] = '{' + text[0][3:]
	overrides.append(text[0][1:-1])
	
	text = ''.join(text[1:])
	overrides = ''.join(overrides)
	if overrides:
		overrides = '{%s}' % overrides
	if PASS == 1:
		chat.vstart, chat.vend = 0, 10
	print('Dialogue: 0,%s,%s,%s,%s,0,0,0,,%s%s' %
	      (time(chat.vstart), time(chat.vend),
	       style, chat.user_id, overrides, text))

if unsupported_commands:
	print('Unhandled commands:', ', '.join(unsupported_commands),
	      file=sys.stderr)

if PASS == 0:
	for font_name, font_chars in chars.items():
		with open(os.path.join('chars', font_name), encoding='utf-8') as file:
			font_chars.update(file.read())
		with open(os.path.join('chars', font_name), 'w', encoding='utf-8') as file:
			file.write(''.join(font_chars))