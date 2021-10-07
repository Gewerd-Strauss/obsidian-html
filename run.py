import sys                  # commandline arguments
import shutil               # used to remove a non-empty directory, copy files
import re                   # regex string finding/replacing
from pathlib import Path    # 
import frontmatter          # remove yaml frontmatter from md files
import markdown             # convert markdown to html
import urllib.parse         # convert link characters like %

 
# python run.py 'C:\Users\Installer\OneDrive\Obsidian\Notes' 'C:\Users\Installer\OneDrive\Obsidian\Notes\Work.md'

# Input
# ------------------------------------------
root_folder = sys.argv[1]   # first folder that contains all markdown files
entrypoint = sys.argv[2]    # The note that will be used as the index.html

if root_folder[-1] == '\\':
    root_folder = root_folder[:-1]


# Config
# ------------------------------------------
md_output_dir   = Path('output/md')
html_output_dir = Path('output/html')
image_suffixes = ['jpg', 'jpeg', 'gif', 'png', 'bmp']

# Preprocess
# ------------------------------------------
# Load all filenames in the root folder.
# This data will be used to convert implicit Obsidian links to proper markdown links. 
files = {}
for path in Path(root_folder).rglob('*'):
    files[path.name] = {'fullpath': str(path), 'processed': False}  
    # ^ the 'processed' switch helps us to avoid infinite loops

# Get html template code. Every note will become a html page, where the body comes from the note's 
# markdown, and the wrapper code from this template.
with open('src/template.html') as f:
    html_template = f.read()


# Remove previous output
output_dir = Path('output')
if output_dir.exists():
    shutil.rmtree(output_dir)

# Recreate tree
md_output_dir.mkdir(parents=True, exist_ok=True)
html_output_dir.mkdir(parents=True, exist_ok=True)

def ConvertPage(page_path):
    # ^ This function creates a proper markdown version of the Obsidian note, 
    #   an html page, and it will recursively call itself on any links in the note.

    # Links can be made in Obsidian without creating the note. 
    # In this case we don't have to do anything.
    if Path(page_path).exists() == False:
        return

    # Load contents of entrypoint and strip frontmatter yaml.
    # If the frontmatter needs to be used at a later date: the frontmatter is loaded into dict keys, 
    # e.g. page['tags']
    page = frontmatter.load(page_path)

    # We need to change "file.md" links to "file.html" for the html version of the output,
    # but only for internal links. Doing this later would be pretty complex.
    # So do all steps below twice, except for some minor differences.
    md_page = page.content
    html_page = page.content

    # Get obsidian links. 
    # This is any string in between [[ and ]], e.g. [[My Note]]
    links = re.findall("(?<=\[\[).+?(?=\])", md_page)

    # Convert proper markdown links from .md to .html in html output, as long as they are .md links that are internal
    # ----
    # Must begin with ](, must end with ) (do not include in match)
    # Must not have \\ or // in the matched string anywhere
    for l in re.findall("(?<=\]\()((?!(.*\/\/|.*\\\\)).*\.md)(?=\))", md_page):
        # remove .md at the end, and add .html
        new_link = ']('+str(l[0][:-3])+'.html)'
        # Replace link in document
        safe_link = re.escape(']('+l[0]+')')
        html_page = re.sub(f"(?<![\[\(])({safe_link})", new_link, html_page)

    # Handle local image links (copy them over to output)
    # ----
    for link in re.findall("(?<=\!\[\]\()(.*)(?=\))", md_page):
        # Only handle local image files (images located in the root folder)
        if urllib.parse.unquote(link) not in files.keys():
            continue

        # Build relative paths
        filepath = files[urllib.parse.unquote(link)]['fullpath']
        relative_path = ConvertFullWindowsPathToRelativeMarkdownPath(filepath, root_folder, "")

        md_filepath = Path('output/md/' + relative_path)
        html_filepath = Path('output/html/' + relative_path)

        # Create folders if necessary
        md_filepath.parent.mkdir(parents=True, exist_ok=True)
        html_filepath.parent.mkdir(parents=True, exist_ok=True)

        # Copy file over
        shutil.copyfile(filepath, md_filepath)
        shutil.copyfile(filepath, html_filepath)

        # Adjust link in page
        new_link = '![]('+relative_path+')'
        safe_link = re.escape('![]('+link+')')
        md_page = re.sub(safe_link, new_link, md_page)
        html_page = re.sub(safe_link, new_link, html_page)
        print(safe_link)
        print(new_link)



    # Replace Obsidian links with proper markdown
    # ----
    for l in links:
        # A link in Obsidian can have the format 'filename|alias'
        # If a link does not have an alias, the link name will function as the alias.
        parts = l.split('|')
        filename = parts[0].split('/')[-1]
        alias = filename
        if len(parts) > 1:
            alias = parts[1]

        # Links can be made in Obsidian without creating the note.
        # When we link to a nonexistant note, link to the not_created.md placeholder instead.
        if filename+'.md' not in files.keys():
            relative_path = '/not_created.md'
        else:
            # Obtain the full path of the file in the directory tree
            # e.g. 'C:\Users\Installer\OneDrive\Obsidian\Notes\Work\Harbor Docs.md'
            full_path = files[filename+'.md']['fullpath']
            relative_path = ConvertFullWindowsPathToRelativeMarkdownPath(full_path, root_folder, entrypoint)

        # Replace Obsidian link with proper markdown link
        url_path = relative_path.replace(' ', '%20')
        md_page = md_page.replace('[['+l+']]', f"[{alias}]({url_path})")

        html_url = urllib.parse.unquote(url_path)
        html_url = html_url.replace('.md', '.html')
        html_url = urllib.parse.quote(html_url)
        html_page = html_page.replace('[['+l+']]', f"[{alias}]({html_url})")

    # Fix newline issue by adding three spaces before any newline
    md_page = md_page.replace("\n", "   \n")
    html_page = html_page.replace("\n", "   \n")

    # Insert markdown links for bare http(s) links (those without the [name](link) format).
    # ----
    # Cannot start with [, (, nor "
    for l in re.findall("(?<![\[\(\"])(http.[^\s]*)", md_page):
        new_md_link = f"[{l}]({l})"
        safe_link = re.escape(l)
        md_page = re.sub(f"(?<![\[\(])({safe_link})", new_md_link, md_page)
        html_page = re.sub(f"(?<![\[\(])({safe_link})", new_md_link, html_page)

    # Remove inline tags, like #ThisIsATag
    # ----
    # Inline tags are # connected to text (so no whitespace nor another #)
    for l in re.findall("#[^\s#`]+", md_page):
        tag = l.replace('.', '').replace('#', '')
        new_md_str = f"**{tag}**"
        new_html_str = f"<span class=\"tag\">{tag}</span>"
        safe_str = re.escape(l)
        md_page = re.sub(safe_str, new_md_str, md_page)
        html_page = re.sub(safe_str, new_html_str, html_page)

    # Compile HTML and other HTML specific transformations
    # ----
    # Convert markdown to html
    html_body = markdown.markdown(html_page, extensions=['extra'])

    # Tag external links
    for l in re.findall(r'(?<=\<a href=")(.*)(?=")', html_body):
        if l[0] == '/':
            # Internal link, skip
            continue

        new_str = f"<a href=\"{l}\" class=\"external-link\""
        safe_str = re.escape(f"<a href=\"{l}\"")
        html_body = re.sub(safe_str, new_str, html_body)

    # Tag not created links
    html_body = html_body.replace('<a href="/not_created.html">', '<a href="/not_created.html" class="nonexistent-link">')

    # Wrap body html in valid html structure from template
    html = html_template.replace('{content}', html_body)

    # Save file
    relative_path = ConvertFullWindowsPathToRelativeMarkdownPath(page_path, root_folder, entrypoint)
    md_filepath = Path('output/md/' + relative_path)
    html_filepath = Path('output/html/' + relative_path.replace('.md', '.html'))

    # Create folder if necessary
    md_filepath.parent.mkdir(parents=True, exist_ok=True)
    html_filepath.parent.mkdir(parents=True, exist_ok=True)
    
    # Write markdown
    with open(md_filepath, 'w', encoding="utf-8") as f:
        f.write(md_page)

    # Write html
    with open(html_filepath, 'w', encoding="utf-8") as f:
        f.write(html)    
    
    # Recurse for every link in the current page
    for l in links:
        # Remove possible alias suffix, folder prefix, and add '.md' to get a valid lookup key
        link_path = l.split('|')[0].split('/')[-1]+'.md'
        
        # Skip non-existent notes and notes that have been processed already
        if link_path not in files.keys():
            continue
        if files[link_path]['processed'] == True:
            continue

        # Mark the file as processed so that it will not be processed again at a later stage
        files[link_path]['processed'] = True         

        # Convert the note that is linked to
        print(f"converting {files[link_path]['fullpath']} (parent {page_path})")
        ConvertPage(files[link_path]['fullpath'])

def ConvertFullWindowsPathToRelativeMarkdownPath(fullwindowspath, root_folder, entrypoint):
    # Convert full Windows path to url link, e.g: 
    # 'C:\Users\Installer\OneDrive\Obsidian\Notes\Work\Harbor Docs.md' --> .replace(root_folder, '') -->
    # '\Work\Harbor Docs.md' --> .replace('\\', '/') -->
    # '/Work/Harbor Docs.md' 
    if fullwindowspath == entrypoint:
        return '/index.md'
    return fullwindowspath.replace(root_folder, '').replace('\\', '/')

# Convert files
# ------------------------------------------
# Start conversion with entrypoint.
# Note: this will mean that any note not (indirectly) linked by the entrypoint will not be included in the output!
ConvertPage(entrypoint)

# Add Extra stuff to the output directories
# ------------------------------------------
shutil.copyfile('src/main.css', 'output/html/main.css')
shutil.copyfile('src/external.svg', 'output/html/external.svg')


with open('src/not_created.html') as f :
    with open ('output/html/not_created.html', 'w', encoding="utf-8") as t:
        t.write(html_template.replace('{content}', f.read()))


