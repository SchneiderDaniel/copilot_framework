import os, argparse, re

def fix_encoding_text(text):
    rep = {'Ã¤':'ä', 'Ã¼':'ü', 'Ã¶':'ö', 'Ã':'ß', 'Ã':'Ä', 'Ã':'Ü', 'Ã':'Ö', 'ÃÂ§':'§', 'Ã§':'§'}
    for k, v in rep.items(): text = text.replace(k, v)
    return text

def repair_encoding(path):
    with open(path, 'r', encoding='utf-8', errors='replace') as f: lines = f.readlines()
    with open(path, 'w', encoding='utf-8') as f: f.writelines([fix_encoding_text(l) for l in lines])
    print(f"Repaired encoding in {path}")

def strip_de(path):
    with open(path, 'r', encoding='utf-8') as f: content = f.read()
    with open(path, 'w', encoding='utf-8') as f: f.write(re.sub(r'msgstr "\[DE\]\s*(.*?)"', r'msgstr "\1"', content))
    print(f"Stripped [DE] prefixes from {path}")

def unfuzzy(path):
    with open(path, 'r', encoding='utf-8') as f: lines = f.readlines()
    with open(path, 'w', encoding='utf-8') as f:
        for line in lines:
            if not line.strip().startswith("#, fuzzy"):
                f.write(line)
    print(f"Removed fuzzy flags from {path}")

def restore_obsolete(path):
    with open(path, 'r', encoding='utf-8') as f: lines = f.readlines()
    obsolete_map, i = {}, 0
    while i < len(lines):
        line = lines[i].strip()
        if line.startswith('#~ msgid "'):
            msgid = line[10:-1]
            i += 1
            while i < len(lines) and lines[i].strip().startswith('#~ "'):
                msgid += lines[i].strip()[4:-1]; i += 1
            if i < len(lines) and lines[i].strip().startswith('#~ msgstr "'):
                msgstr = lines[i].strip()[11:-1]; i += 1
                while i < len(lines) and lines[i].strip().startswith('#~ "'):
                    msgstr += lines[i].strip()[4:-1]; i += 1
                if msgstr: obsolete_map[msgid] = msgstr
        else: i += 1
    if not obsolete_map: return print("No obsolete translations found.")
    new_lines, i, restored = [], 0, 0
    while i < len(lines):
        line = lines[i]
        if line.strip().startswith('msgid "'):
            msgid = line.strip()[7:-1]; temp = [line]; i += 1
            while i < len(lines) and lines[i].strip().startswith('"'):
                msgid += lines[i].strip()[1:-1]; temp.append(lines[i]); i += 1
            while i < len(lines) and not lines[i].strip().startswith('msgstr "'):
                temp.append(lines[i]); i += 1
            if i < len(lines) and lines[i].strip().startswith('msgstr "'):
                curr = lines[i].strip()[8:-1]; start = i; i += 1
                while i < len(lines) and lines[i].strip().startswith('"'):
                    curr += lines[i].strip()[1:-1]; i += 1
                if (not curr or curr == msgid) and msgid in obsolete_map:
                    temp.append(f'msgstr "{obsolete_map[msgid]}"\n'); restored += 1
                else: temp.extend(lines[start:i])
            new_lines.extend(temp)
        else: new_lines.append(line); i += 1
    with open(path, 'w', encoding='utf-8') as f: f.writelines(new_lines)
    print(f"Restored {restored} translations in {path}")

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("path"); p.add_argument("--repair", action="store_true")
    p.add_argument("--strip-de", action="store_true"); p.add_argument("--restore-obsolete", action="store_true")
    p.add_argument("--unfuzzy", action="store_true")
    args = p.parse_args()
    if args.unfuzzy: unfuzzy(args.path)
    if args.restore_obsolete: restore_obsolete(args.path)
    if args.strip_de: strip_de(args.path)
    if args.repair: repair_encoding(args.path)
