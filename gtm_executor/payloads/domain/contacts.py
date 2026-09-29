"""CSV cells are inert strings, not instructions or evidence of consent."""
import csv
import re
from pathlib import Path
from .state import digest

COLUMNS = ['Name','Email','Category','Note','Highlight']
EMAIL = re.compile(r'[^\s@,;<>]+@[^\s@,;<>]+\.[^\s@,;<>]+')


def import_contacts(state, path):
    path = Path(path).expanduser()
    if path.stat().st_size > 10_000_000:
        raise ValueError('Contact file is too large')
    content = path.read_bytes()
    version = digest(content.decode('utf-8-sig'))
    if state.get('meta','contacts_version') == version:
        return
    with path.open(newline='',encoding='utf-8-sig') as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != COLUMNS:
            raise ValueError('Contacts CSV must contain Name, Email, Category, Note, Highlight')
        valid, invalid = {}, []
        for row_number,row in enumerate(reader,2):
            if row_number > 10001 or None in row or any(v is None or len(v)>4000 for v in row.values()):
                raise ValueError('Invalid or oversized contact row')
            email = row['Email'].strip().casefold()
            if len(email) > 254 or not EMAIL.fullmatch(email):
                invalid.append({'row':row_number,'values':row,'reason':'invalid_email'})
            else:
                valid[email] = row
    # A current snapshot excludes recipients removed from a replacement input.
    state.put('meta','contacts',valid)
    state.put('meta','quarantine',invalid)
    state.put('meta','contacts_version',version)


def segment(row):
    if row['Category'].strip().casefold() == 'investor':
        return 'investor'
    if row['Category'].strip().casefold() == 'client':
        return 'customer'
    return 'education_partner'


def select_recipients(state, audience, limit):
    if audience not in {'customer','education_partner','investor'}:
        raise ValueError('Unsupported audience segment')
    return [email for email,row in sorted(state.get('meta','contacts',{}).items())
            if segment(row) == audience and not state.suppressed(email)][:limit]
