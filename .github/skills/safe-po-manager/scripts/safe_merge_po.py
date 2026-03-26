import os
import sys
import polib
import argparse

def safe_merge(po_path, pot_path, verbose=False):
    """
    Safely merges a POT file into a PO file.
    Preserves all existing msgstr values and revives obsolete entries if they reappear.
    Does NOT delete any entries from the PO file.
    """
    if not os.path.exists(po_path):
        print(f"Error: PO file not found at {po_path}")
        return False
    if not os.path.exists(pot_path):
        print(f"Error: POT file not found at {pot_path}")
        return False

    po = polib.pofile(po_path)
    pot = polib.pofile(pot_path)
    
    modified = False
    new_entries_count = 0
    revived_entries_count = 0
    updated_metadata_count = 0

    # 1. Map existing entries for fast lookup
    po_entries = {entry.msgid: entry for entry in po}
    obsolete_entries = {entry.msgid: entry for entry in po.obsolete_entries()}

    # 2. Process all entries from the POT file (the template)
    for pot_entry in pot:
        if pot_entry.msgid in po_entries:
            # Entry exists, update occurrences and comments if they changed
            po_entry = po_entries[pot_entry.msgid]
            if po_entry.occurrences != pot_entry.occurrences:
                po_entry.occurrences = pot_entry.occurrences
                modified = True
                updated_metadata_count += 1
        elif pot_entry.msgid in obsolete_entries:
            # Revive obsolete entry
            obs_entry = obsolete_entries[pot_entry.msgid]
            new_entry = polib.POEntry(
                msgid=obs_entry.msgid,
                msgstr=obs_entry.msgstr,
                comment=pot_entry.comment,
                tcomment=obs_entry.tcomment,
                occurrences=pot_entry.occurrences,
                flags=obs_entry.flags
            )
            # Remove from obsolete and add to main
            po.remove(obs_entry)
            po.append(new_entry)
            modified = True
            revived_entries_count += 1
            if verbose:
                print(f"Revived entry: {pot_entry.msgid}")
        else:
            # Truly new entry
            po.append(pot_entry)
            modified = True
            new_entries_count += 1
            if verbose:
                print(f"Added new entry: {pot_entry.msgid}")

    if modified:
        po.save()
        print(f"Success: Merged {pot_path} into {po_path}")
        print(f"  - New entries: {new_entries_count}")
        print(f"  - Revived entries: {revived_entries_count}")
        print(f"  - Updated occurrences: {updated_metadata_count}")
    else:
        print("No changes needed. PO file is up to date.")
    
    return True

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Safely merge POT into PO without losing content.")
    parser.add_argument("po", help="Path to the .po file")
    parser.add_argument("pot", help="Path to the .pot file")
    parser.add_argument("-v", "--verbose", action="store_true", help="Increase output verbosity")
    
    args = parser.parse_args()
    
    try:
        success = safe_merge(args.po, args.pot, args.verbose)
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"Fatal Error: {str(e)}")
        sys.exit(1)
