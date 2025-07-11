#!/usr/bin/env python

# generates android metadata from README.md, CHANGES.md and screenshots

from pathlib import Path
import os
import contextlib

def program_exists(program):
    import shutil
    return shutil.which(program) is not None

def mkdir(path):
    path.mkdir(exist_ok=True, parents=True)

def version_to_code(version, epoch=0) -> str:
    return ''.join(
        f"{int(v):02d}"
        for v in version.split('.')
    )

def last_version(metadata_path):
    last_code = list(sorted((metadata_path/'changelogs').glob('*txt')))[-1].stem
    digits = 2
    return '.'.join(
        str(int(last_code[i:i+digits]))
        for i in range(0,len(last_code),digits)
    )

def cp(origin, target):
    origin=Path(origin)
    target=Path(target)
    print(f":: \033[34;1m{origin} -> {target}\033[0m")
    mkdir(target.parent)
    target.write_bytes(origin.read_bytes())

def dump(file, content):
    print(f":: \033[34;1m{file}\033[0m\n{content}")
    file.write_text(content)

def generateDescriptions(metadata_path):
    readme = Path("README.md").read_text()
    readme = readme.split('#',1)[1]
    readme_lines = readme.splitlines()
    title = readme_lines.pop(0).replace('#', '').strip().replace('-',' ').title()
    readme_lines = [ line for line in readme_lines if not line.strip().startswith("![") ]
    while not readme_lines[0].strip():
        readme_lines.pop(0)
    short_description = readme_lines.pop(0)

    full_description = '\n'.join(readme_lines).strip()
    dump(metadata_path/"title.txt", title)
    dump(metadata_path/"short_description.txt", short_description)
    dump(metadata_path/"full_description.txt", full_description)

def generateChangelogs(metadata_path: Path):
    def process_chapter(chapter):
        heading, body = chapter.split('\n', 1)
        heading = heading.strip()
        version = heading.split()[0]
        return version, body.strip()

    changelog=Path("CHANGES.md").read_text()

    changelog_path = metadata_path/"changelogs"
    mkdir(changelog_path)

    changelog_chapters = changelog.split("##")[1:]
    for chapter in changelog_chapters:
        version, body = process_chapter(chapter)
        if not version[0].isnumeric():
            # Unreleased
            continue
        version_code = version_to_code(version)
        dump((changelog_path/version_code).with_suffix('.txt'), "##" + chapter)

def generateImages(metadata_path):
    images_path = metadata_path/'images'/'phoneScreenshots'
    for screenshot in Path().glob("screenshots/*png"):
        target = images_path/screenshot.name
        cp(screenshot, target)

def generateIcon(metadata_path):
    import subprocess
    pad=300
    subprocess.run([
        'convert',
        'icon.png',
        '-set', 'option:distort:viewport',
        f'%[fx:w+{2*pad}]x%[fx:h+{2*pad}]-{pad}-{pad}',
        '-virtual-pixel',
        'Edge',
        '-distort',
        'SRT',
        '0',
        '+repage',
        str(metadata_path/'images'/'icon.png')
    ])


def adapt_android_preset(metadata_path):
    appname = (metadata_path/'title.txt').read_text()
    version = last_version(metadata_path)
    code = version_to_code(version)
    export_path = (Path('build/android')/appname.replace(" ", "-").lower()).with_suffix('.apk')
    unique_name = 'net.canvoki.godot_dice_roller'
    icon_main = str(metadata_path/'images'/'icon.png')

    import configparser
    import json

    def get(section, name):
        return json.loads(section.get(name, 'null'))
    def set(section, name, value):
        section[name] = json.dumps(value)

    def get_named_preset(config, name):
        for section in config.sections():
            section_name = get(config[section], 'name')
            print(f"Found {section} {section_name} {name}")
            if section_name != name: continue
            return config[section], config[section+".options"]
        return None, None

    export_presets = configparser.ConfigParser()
    export_presets.read('tools/export_presets_template.cfg')
    preset, options = get_named_preset(export_presets, "Android")
    set(preset, 'export_path', str(export_path))
    set(options, 'version/name', version)
    set(options, 'version/code', code)
    set(options, 'package/name', appname)
    set(options, 'package/unique_name', unique_name)
    set(options, 'launcher_icons/main_192x192', icon_main)
    presets_file = Path("export_presets.cfg")
    with presets_file.open('w') as output:
        export_presets.write(output)
    modified = presets_file.read_text().replace(" = ", "=")
    presets_file.write_text(modified)

def updateSplashVersion(metadata_path):
    version = last_version(metadata_path)
    splash_svgfile = Path('examples/dice_roller/splash.svg')

    from lxml import etree

    nsmap = dict(
        svg='http://www.w3.org/2000/svg',
        inkscape="http://www.inkscape.org/namespaces/inkscape",
        sodipodi="http://sodipodi.sourceforge.net/DTD/sodipodi-0.dtd",
        xlink="http://www.w3.org/1999/xlink",
    )

    parser = etree.XMLParser(remove_blank_text=True)
    tree = etree.parse(splash_svgfile, parser)
    root = tree.getroot()

    el = root.xpath("//svg:text[@id='version']/svg:tspan", namespaces=nsmap)
    if not el:
        print("Warning: No element with id version found is splash screen svg")
        return
    if el[0].text == version:
        print(f"Skipping splash screen version update, already {version}")
        return

    print(f"Updating splash screen version from {el[0].text} to {version}")
    el[0].text = version
    for prefix, nsurl in nsmap.items():
        etree.register_namespace(prefix, nsurl)
    print(f"Generating {splash_svgfile}...")
    tree.write(splash_svgfile, encoding='utf-8', xml_declaration=True, pretty_print=True)
    png_file = splash_svgfile.with_suffix(".png")
    print(f"Generating {png_file}...")

    if not program_exists("inkscape"):
        print("WARNING: Inkscape not detected. Splash png not updated.")
        return

    import subprocess
    subprocess.run([
        'inkscape',
        str(splash_svgfile),
        '--export-type=png',
        '--export-filename='+str(png_file)
    ])

def updateSplash(metadata_path):
    updateSplashVersion(metadata_path)
    cp(
        origin = 'examples/dice_roller/splash.png',
        target = metadata_path/'images'/'featureGraphic.png',
    )


def generateMetadata():
    metadata_path = Path("fastlane/metadata/android/en-US")
    mkdir(metadata_path)
    Path('fastlane/.gdignore').write_text('')
    generateDescriptions(metadata_path)
    generateChangelogs(metadata_path)
    updateSplash(metadata_path)
    generateImages(metadata_path)
    generateIcon(metadata_path)
    adapt_android_preset(metadata_path)



if __name__ == '__main__':
    generateMetadata()




