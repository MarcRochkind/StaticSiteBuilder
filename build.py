# StaticSiteBuilder
# Marc Rochkind, 20-Feb-2024 and later
# MIT license
# https://github.com/MarcRochkind/StaticSiteBuilder

from tkinter import *
from tkinter import ttk
from tkinter import filedialog
from tkinter import messagebox
from tkinter import scrolledtext
from tkinter.simpledialog import askstring
import webbrowser
import os, re, html
import markdown
import time    
import shutil
import pysftp # https://pysftp.readthedocs.io/en/release_0.2.9/pysftp.html
from pathlib import Path

current_page = None
DATA_FOLDER = 'data'
PAGES_FOLDER = '.'
HOME_PAGE = 'index'
site_folder = None
starting_folder = os. getcwd()
# Code is present to handle SFTP uploads, but it is not enabled (see process_settings()).
# It was written because an earlier version supported building sites for hosts with servers,
# but now only serverless hosts are handled.
sftp = None # always
status_label = None
dirty = False
want_prevnext = False
menu_list = []

def delete_status():
	status_label.config(text='')

def status(s):
	status_label.config(text=s)
	status_label.after(3000, delete_status)

def html_file(page):
	ext = '.html'
	return page + ext

def html_path(page):
	return os.path.join(PAGES_FOLDER, html_file(page))

def text_path(page):
	return os.path.join(DATA_FOLDER, page + '.txt')

def open_site():
	global site_folder

	save_current_page()
	site_folder = filedialog.askdirectory()
	if not site_folder:
		return;
	os.chdir(site_folder)
	if not os.path.exists(DATA_FOLDER):
		new_site_with_folder(site_folder)
	else:
		initialize_site()
	content_label.config(text = f'Content for site "{os.path.basename(site_folder)}"')

def new_site():
	new_site_with_folder(None)

def process_js_files():
	path = os.path.join(PAGES_FOLDER, 'masonry.pkgd.min.js')
	shutil.copyfile(os.path.join(starting_folder, 'masonry.pkgd.min.js'), path)
	sftp_put(path)
	path = os.path.join(PAGES_FOLDER, 'imagesloaded.pkgd.min.js')
	shutil.copyfile(os.path.join(starting_folder, 'imagesloaded.pkgd.min.js'), path)
	sftp_put(path)

def new_site_with_folder(folder):
	global site_folder

	save_current_page()
	current_page = None
	content_label.config(text = '')

	if folder:
		site_folder = site_folder
	else:
		site_folder = filedialog.askdirectory()
	if not site_folder:
		return;
	os.chdir(site_folder)
	if not os.path.exists(DATA_FOLDER):
		os.mkdir(DATA_FOLDER)
	if not os.path.exists(PAGES_FOLDER):
		os.mkdir(PAGES_FOLDER)
	process_js_files()
	with open(text_path('@header'), 'w') as f:
		f.write('**Page Header**\n')
	save_html_page('@header')
	with open(text_path('@footer'), 'w') as f:
		f.write('*Page Footer*\n')
	save_html_page('@footer')
	with open(text_path('@settings'), 'w') as f:
		f.write('\n')
	with open(text_path('@site.css'), 'w') as f:
		f.write('''#page-footer {
}
#page-header {
}
#menu {
}
#title {
}
#header-hr {
}
#footer-hr {
}
#main {
}
#main p {
}
			''')
	save_html_page('@site.css')
	with open(text_path('@menu'), 'w') as f:
		f.write(HOME_PAGE + '\n')
	with open(text_path(HOME_PAGE), 'w') as f:
		f.write('@title Home Page\nThis is the home page.\n')
	save_html_page('@menu')
	save_html_page(HOME_PAGE)
	initialize_site()

def initialize_site():
	global pages, current_page

	pagetext.delete("1.0", END)
	current_page = None
	pages = []
	with os.scandir(DATA_FOLDER) as it:
		for entry in it:
			if entry.name.endswith('.txt'):
				(f, e) = os.path.splitext(entry.name)
				pages.append(f)
	populate_pages_listbox()
	process_settings();

def populate_pages_listbox():
	global pages

	pages = sorted(pages, key=str.casefold)
	pagelistbox.delete(0,END)
	for p in pages:
		pagelistbox.insert(END, p)

def select_page():
	global current_page, site_folder

	save_current_page()
	n = pagelistbox.curselection()
	if n:
		current_page = pagelistbox.get(n[0])
		with open(os.path.join(DATA_FOLDER, current_page + '.txt.'), 'r') as f:
			s = f.read()
		pagetext.delete("1.0", END)
		pagetext.insert(END, s)
		reset_changed()
		content_label.config(text = f'Content for site "{os.path.basename(site_folder)}", page "{current_page}"')
	else:
		print("No item selected")

def get_prevnext(page):
	global want_prevnext, menu_list

	if not want_prevnext:
		return (None, None)
	prev_link = None
	next_link = None
	want_next = False
	for p in menu_list:
		if p == page:
			want_next = True
		else:
			if want_next:
				next_link = p + '.html'
				break
			else:
				prev_link = p + '.html'
	return (prev_link, next_link)

def write_html(page, s, expand = True):
	(prev_link, next_link) = get_prevnext(page)
	local_path = html_path(page)
	h = build_html(page, s, prev_link, next_link, expand)
	with open(local_path, 'w') as f:
		f.write(h)
	sftp_put(local_path)

def save_html_page(page, expand = True):
	with open(text_path(page), 'r') as f:
		text = f.read()
	if (page[0] != '@'):
		write_html(page, text, expand)
	elif page == '@site.css':
		css_path = os.path.join(PAGES_FOLDER, 'site.css')
		with open(css_path, 'w') as f:
			f.write(text);
		sftp_put(css_path)
	elif page == '@settings':
		process_settings()
	elif page == '@menu':
		process_menu();
	elif page == '@header' or page == '@footer':
		with open(text_path(page), 'r') as f:
			path = html_path(page[1:])
			s = f.read()
			with open(path, 'w') as out:
				out.write(markdown.markdown(s))
			sftp_put(path)

def save_current_page():
	global num_successful

	if not dirty:
		return
	num_successful = 0
	if current_page:
		text = pagetext.get("1.0", END)
		with open(text_path(current_page), 'w') as f:
			f.write(text.strip())
		save_html_page(current_page)
	reset_changed()
	process_menu() # in case title changed
	if sftp and num_successful == 2:
		status('Uploaded OK')

# The @settings.txt file is for SFTP parameters, but SFTP is not enabled.
# The file is still present in case some other settings are introduced in the future.
def process_settings():
	global sftp_host, sftp_username, sftp_password, sftp_path, sftp, want_prevnext

	want_prevnext = False
	# disable sftp -- using S3 only
	sftp = None
	sftp_host = None
	sftp_username = None
	sftp_password = None
	sftp_path = None
	with open(text_path('@settings'), 'r') as f:
		for s in f:
			m = re.match('^@([^ ]*) *(.*)$', s)
			if m:
				match m.group(1):
					case 'host':
						sftp_host = m.group(2).strip()
					case 'username':
						sftp_username = m.group(2).strip()
					case 'password':
						sftp_password = m.group(2).strip()
					case 'path':
						sftp_path = m.group(2).strip()
					case 'prevnext':
						want_prevnext = True
						process_menu()
	if sftp_host and sftp_username and sftp_password and sftp_path:
		try:
			cnopts = pysftp.CnOpts()
			cnopts.hostkeys = None
			sftp = pysftp.Connection(sftp_host, username=sftp_username, password=sftp_password, port=7822, cnopts=cnopts)
			sftp.chdir(sftp_path) # using default_path arg to constructor doesn't report errors
		except Exception as err:
			messagebox.showerror("FTP Connection Error", err)
			sftp = None
		else:
			status(f'Connected to {sftp_host} at {sftp_path}')

def sftp_put(path):
	global num_successful

	if sftp:
		try:
			sftp.put(path)
		except Exception as err:
			messagebox.showerror("FTP Put Error", err)
		else:
			num_successful = num_successful + 1

def split_at_word(s, n):
	r = ''
	w = s.split()
	for x in w:
		r += x + ' '
		if len(r) >= n:
			r += '<br>'
			n = 2 * n + 4
	return r.strip()

def process_menu():
	global menu_list

	menu_list = []
	html = ''
	have_menu = False
	try:
		with open(text_path('@menu'), 'r') as fm:
			for p in fm:
				p = p.strip()
				if len(p) == 0:
					continue
				if p[0] == '@':
					continue
				if p[0] == '<':
					html += p + '\n'
				else:
					menu_list.append(p)
					path = text_path(p)
					s = None
					with open(path, 'r') as f:
						s = f.read()
					if not s:
						s = p
					(title, t) = extract_title(s)
					if title == '':
						continue
					file = html_file(p)
					t = split_at_word(title, 40)
					html += f'<p id="m-{p}"><a href="{file}">{t}</a>\n'
				have_menu = True
		if have_menu:
			path = html_path('menu')
			with open(path, 'w') as out:
				out.write(html + '\n')
			sftp_put(path)
	except Exception as err:
		messagebox.showerror("Error", '@menu page error: ' + str(err))

def has_content(page):
	with open(text_path(page), 'r') as f:
		s = f.read().strip()
	return len(s) > 0

def build_menu(expand = True):
	with open(text_path('@menu'), 'r') as f:
		m = f.read().strip()
	if len(m) == 0:
		return None;
	html = '''<div id=menu class=topnav>
'''
	if (expand):
		html += get_pages_file('menu')
	else:
		html += '\n<!--#include file="menu.shtml" -->\n'
	html += f'''
</div>
'''
	return html

def extract_title(s):
	(params, rest) = get_params(s)
	if 'title' in params:
		title = params['title']
	else:
		title = ''
	return(title, rest)

def get_params(s):
	params = {}
	s = s.strip()
	while True:
		m = re.match('(?s)^@(\w*)([^\n]*)(.*)', s)
		if not m:
			break
		params[m.group(1)] = m.group(2).strip()
		s = m.group(3).strip()
	if not 'title' in params:
		params['title'] = ''
	return (params, s)

def get_pages_file(f):
	if (f == 'site.css'):
		path = os.path.join(PAGES_FOLDER, 'site.css')
	else:
		path = html_path(f)
	return Path(path).read_text()

def build_html(page, s, prev_link, next_link, expand = True):
	(params, mtext) = get_params(s)
	title = params['title']
	nomenu = 'nomenu' in params
	colors = 'colors' in params
	masonry = 'masonry' in params
	if masonry:
		masonry_options = params['masonry']
	else:
		masonry_options = ''
	while True:
		mm = re.match('(?s)^(.*)\{([^}]*)\|([^}]*)\}(.*)$', mtext)
		if not mm:
			break
		mtext = mm.group(1) + f'<a href="{mm.group(2)}.html">{mm.group(3)}</a>' + mm.group(4)
	sidebar = build_menu(expand)
	want_table = sidebar and not nomenu
	epoch_time = str(time.time())
	html1 = f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>{title}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Abril+Fatface&family=Patua+One&display=swap" rel="stylesheet">
'''
	if masonry:
		html1 += '''
<script type="text/javascript" src="masonry.pkgd.min.js"></script>
<script type="text/javascript" src="imagesloaded.pkgd.min.js"></script>'''
	html1 += f'''
<style>
	.top-table {{
		border-collapse: collapse;
	}}
	#sidebar-td {{
		border-right: 1px solid gray;
		padding-right: 10px;
		vertical-align: top;
	}}
	#main-td {{
		padding-left: 10px;
		vertical-align: top;
	}}
	#hamburger-icon, #hamburger-icon-x {{
		margin-top: 0px;
		display: none;
		cursor: pointer;
		float: right;
	}}
	#hamburger-icon-x {{
		margin-top: 6px;
		margin-right: 8px;
		font-size: 26px;
	}}
	#hamburger-icon div {{
		width: 35px;
		height: 3px;
		background-color: black;
		margin: 6px 0; /* top right bottom left */
		xtransition: 0.4s;
	}}
	#menu {{
		background-color: #eeee;
		padding: 5px;
		overflow: auto;
		max-height: 500px;
	}}
	#menu p {{
		margin-bottom: 5px;
	}}
	#menu a:visited, #menu a:link, #menu a:active {{
		text-decoration: none;
		color: black;
  	}}
	#menu a:hover {{
		text-decoration: none;
		color: blue;
  	}}
	body {{
		max-width: 800px;
		font-family: sans-serif;
		font-size: 14px;
	}}
	#menu {{
		font-size: 12px;
	}}
	#page-footer {{
		font-size: 12px;
	}}
	#page-header {{
		font-size: 20px;
	}}
	.grid-item {{
		width: 300px;
		border-radius: 10px;
		background-color: #eeeeee;
		padding: 5px;
		margin-bottom: 5px;
		overflow: hidden;
	}}

img.left, img.right {{
	margin-right: 5px;
	margin-bottom: 5px;
}}
img.left {{
	float: left;
	margin-right: 10px;
}}
img.right {{
	float: right;
	margin-left: 10px;
}}
@media screen and (max-device-width:600px) {{
	#sidebar-td {{
		border-right: none;
		padding-right: 0;
	}}
	#hamburger-icon {{
		display: block;
	}}
	#hamburger-icon-x {{
		display: none;
	}}
	#menu {{
		display: none;
	}}
	#page-header {{
		font-size: 16px;
	}}
}}
'''
	if masonry:
		html1 += '''
	body {
		max-width: none;
	}
'''
	if (expand):
		html1 += get_pages_file('site.css')
	else:
		html1 += '\n<!--#include file="site.css" -->\n'
	html1 += f'''
</style>
<script>
let menu_shown = false;
function toggleMobileMenu() {{
	menu_shown = !menu_shown;
	let ph = document.getElementById("page-header");
	let main = document.getElementById("main-td");
	let nb = document.getElementById("menu");
	let hi = document.getElementById("hamburger-icon");
	let hix = document.getElementById("hamburger-icon-x");
	if (menu_shown/*c.includes('responsive')*/) {{
		ph.style.display = 'none';
		main.style.display = 'none';
		nb.style.display = 'block';
		hi.style.display = 'none';
		hix.style.display = 'block';
	}}
	else {{
		ph.style.display = 'block';
		main.style.display = 'block';
		nb.style.display = 'none';
		hi.style.display = 'block';
		hix.style.display = 'none';
	}}
}}
function setcolors() {{
	let x = [0, 90, 180, 270, 30, 120, 210, 300, 60, 150, 240, 330];
	for (let id = 1; id <= 100; id++) {{
		let hsl = "hsl(" + x[(id - 1) % 12] + " 100% 90%)";
		let p = document.getElementById('cell' + id);
		if (p) {{
			p.style.backgroundColor = hsl;
			p.style.display = 'block';
		}}
		else
			break;
	}}
}}
function bodyloadedmasonry() {{
	let grid = document.querySelector('.grid');
	imagesLoaded(grid,
		function () {{
			let msnry = new Masonry(grid,
				{{
					// options
					itemSelector: '.grid-item',
					columnWidth: 20,
					{masonry_options}
				}}
			);
		}}
	);
'''
	if colors:
		html1 += f'''
	setcolors();
'''
		celldisplay = 'none'
	else:
		celldisplay = 'block'
	html1 += f'''
	bodyloaded();
}}
function bodyloaded() {{
	let m = document.getElementById("menu");
	let ph = document.getElementById("page-header");
	let mi =  document.getElementById("m-{page}");
	if (m && ph && mi) {{
		let rect = ph.getBoundingClientRect();
		m.style.maxHeight = (window.innerHeight - ph.offsetHeight - rect.top - 30) + 'px';
		mi.scrollIntoView({{
            behavior: 'auto',
            block: 'center',
            inline: 'center'
        }});
		mi.style.backgroundColor = '#baa9cc';
	}}
}}
</script>
</head>'''
	if masonry:
		html1 += '\n<body onload="bodyloadedmasonry()">'
	else:
		html1 += '\n<body onload="bodyloaded()">'
	html1 += f'''
<div id="hamburger-icon" onclick="toggleMobileMenu()">
	<div class="bar1"></div>
	<div class="bar2"></div>
	<div class="bar3"></div>
</div>
<div id="hamburger-icon-x" onclick="toggleMobileMenu()">
	X
</div>'''
	if has_content('@header'):
		html1 += '''
<div id=page-header>
'''
	if (expand):
		html1 += get_pages_file('header')
	else:
		html1 += '\n<!--#include file="header.shtml" -->\n'
	html1 += f'''
<hr id=header-hr>
</div>'''
	if want_table:
		if masonry:
			style = "style='width: 8000px;'"
		else:
			style = ''
		html1 += f'''
<table border=0 class=top-table>
<tr><td id=sidebar-td nowrap>{sidebar}</td><td id=main-td {style}>
'''
	if prev_link or next_link:
		if prev_link:
			html1 += f'<a href="{prev_link}">Prev</a>' # &#8678;
		else:
			html1 += 'Prev'
		html1 += '&nbsp;&nbsp;&nbsp;&nbsp;'
		if next_link:
			html1 += f'<a href="{next_link}">Next</a>' # &#8680;
		else:
			html1 += 'Next'
	if title != 'Home':
		html1 += f'''
<h1 id=title>{title}</h1>
'''
	html1 += f'''
<div id=main>
'''
	if want_table:
		html2 = '</div></td></tr></table>'
	else:
		html2 = '</div>'
	if has_content('@footer'):
		html2 += '''
<hr id=footer-hr>
<div id=page-footer>
'''
	if (expand):
		html2 += get_pages_file('footer')
	else:
		html2 += '\n<!--#include file="footer.shtml" -->\n'
	html2 += f'''
</div>'''
	html2 += '''
</body>
</html>
'''
	mtext = process_commands(mtext, celldisplay)
	return html1 + mtext + html2

def process_commands(mtext, celldisplay):
	first_cell = True
	had_cell = False
	close_anchor = False
	html = ''
	t = ''
	idnum = 1
	for s in mtext.splitlines():
		m = re.match('^%%([^ ]*) *([^ ]*) *([^ ]*) *([^ ]*)$', s)
		anchor = re.match('^https:.*$', s)
		if m:
			arg1 = m.group(2)
			arg2 = m.group(3)
			arg3 = m.group(4)
			match m.group(1):
				case 'cell':
					html += markdown.markdown(t)
					t = ''
					if first_cell:
						html += '<div class=grid>\n'
						had_cell = True
						first_cell = False;
					else:
						html += '</div>\n'
						if close_anchor:
							html += '</a>\n'
							close_anchor = False
					if len(arg2) > 0:
						html += f'<a class="cell-anchor" href="{arg2}">\n'
						close_anchor = True
					html += f'<div id=cell{idnum} class="grid-item {arg1}" style="display: {celldisplay};">\n'
					idnum += 1
				case 'image':
					html += markdown.markdown(t)
					t = ''
					if len(arg3) > 0:
						w = f' style="max-width:{arg3}px;"'
					else:
						w = ''
					html += f'\n<img src="{arg1}" class="{arg2}" {w}>\n'
				case 'clear':
					html += markdown.markdown(t)
					t = ''
					html += '\n<br clear=all>\n'
		elif anchor:
			t += f'\n<p style="margin-left: 20px;"><a href="{anchor.group(0)}" target=_blank>{anchor.group(0)}</a></p>\n'
		else:
			t = t + s + '\n'
	html += markdown.markdown(t)
	if had_cell:
		html += '</div></div>\n'
	return html

# Following were once used, but no longer. Code is here in case it's found to be useful someday.

# def show_current_page():
# 	save_current_page()
# 	# for p in pages:
# 	# 	rewrite_page(p)
# 	if not current_page:
# 		messagebox.showerror("Error", 'No page to show')
# 	else:
# 		html_file = html_path(current_page)
# 		webbrowser.open_new(html_file)

# def show_site():
# 	save_current_page()
# 	home_page = None
# 	for p in pages:
# 		if not home_page:
# 			home_page = p
# 		# rewrite_page(p)
# 	if os.path.exists(html_path(HOME_PAGE)):
# 		home_page = HOME_PAGE
# 	if not home_page:
# 		messagebox.showerror("Error", 'No home page')
# 	else:
# 		html_file = html_path(home_page)
# 		webbrowser.open_new(html_file)

def rebuild_all():
	upload_site(True)

def upload_site(expand = True): # no longer really uploads -- just rebuilds
	global num_successful

	num_successful = 0;
	num_expected = len(pages) + 1 # settings not uploaded; two js files are
	save_current_page()
	for p in pages:
		if p != '@settings' and p[0] == '@':
			save_html_page(p, expand)
	for p in pages:
		if p[0] != '@':
			save_html_page(p, expand)
	process_js_files()
	if sftp:
		if num_successful == num_expected:
			status(f'Uploaded OK ({num_successful} pages)')
		else:
			status(f'ERROR: Uploaded {num_successful} of {num_expected} pages')
	else:
		status(f'Rebuilt')

def new_page():
	if not site_folder:
		messagebox.showerror("Error", 'No site is open.')
		return
	save_current_page()
	page = askstring('New Page', 'Tag (not title) for new page')
	path = text_path(page)
	if os.path.exists(path):
		messagebox.showerror("Error", 'Page already exists.')
		return
	text = f'@title Page {page}\nRest of page'
	with open(path, 'w') as f:
		f.write(text)
	sftp_put(path)
	write_html(page, text)
	pages.append(page)
	populate_pages_listbox()
	index = pagelistbox.get(0, "end").index(page)
	pagelistbox.selection_set(index)
	select_page()
	menu_path = text_path('@menu')
	# read all the lines to get rid of blank ones
	with open(menu_path, 'r') as f:
		menu = f.readlines()
	with open(menu_path, 'w') as f:
		for p in menu:
			p = p.strip()
			if len(p) == 0:
				continue
			f.write(p + '\n')
		f.write(page + '\n')
	process_menu()

pages = []

def on_closing():
	save_current_page()
	root.destroy()

def on_changed(event=None):
	global dirty

	if pagetext.edit_modified():
		dirty = True

def reset_changed():
	global dirty

	pagetext.edit_modified(False)
	dirty = False

root = Tk()
root.title("StaticSiteBuilder")
root.protocol("WM_DELETE_WINDOW", on_closing)

fr = Frame(root)
opensite_button = Button(fr, text="Open Site", command=open_site)
opensite_button.pack(side=LEFT, padx=10, pady=10)
newsite_button = Button(fr, text="New Site", command=new_site)
newsite_button.pack(padx=10, pady=10)
fr.grid(row=0, column=0, sticky='w')

fr = Frame(root)
label1 = Label(fr, text='Pages')
label1.pack()
border_color = Frame(fr, background="black")
pagelistbox = Listbox(border_color, width=30, height=18)
populate_pages_listbox()
border_color.pack() #grid(row=2, column=0, sticky='n')
pagelistbox.pack(padx=1, pady=1) #grid(row=2, column=0, padx=1, pady=1, sticky='n')
fr.grid(row=1, column=0, sticky='ns')

fr = Frame(root)
select_button = Button(fr, text="Select Page", command=select_page)
select_button.pack(side=LEFT, padx=10, pady=10)
new_button = Button(fr, text="New Page", command=new_page)
new_button.pack(padx=10, pady=10)
fr.grid(row=1, column=0, sticky='s')

content_label = Label(root, text='Content')
content_label.grid(row=0, column=1)
pagetext = scrolledtext.ScrolledText(undo=True, wrap=WORD)
#pagetext.pack(expand=True, fill=BOTH)
pagetext.grid(row=1, column=1, sticky='nsew')
pagetext.bind("<<Modified>>", on_changed)

fr = Frame(root)
save_button = Button(fr, text="Save Page", command=save_current_page)
save_button.pack(side=LEFT, padx=10, pady=10)
status_label = Label(fr, text='')
status_label.pack(padx=10, pady=10)
fr.grid(row=2, column=1, sticky='w')
expand_button = Button(root, text="Rebuild All", command=rebuild_all)
expand_button.grid(row=2, column=1, sticky='e', padx=10, pady=10)

root.grid_columnconfigure(1, weight=1)
root.grid_rowconfigure(1, weight=1)

root.minsize(1000, 700)

root.mainloop()