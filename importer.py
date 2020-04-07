#!/usr/bin/env python

from flask import Flask
from sqlalchemy_utils import database_exists, create_database
from sqlalchemy.engine.url import make_url
from sqlalchemy.exc import OperationalError
from werkzeug.utils import secure_filename

import yaml
import shutil
import os
import sys
import hashlib
import argparse

REQ_FIELDS = ['name', 'description', 'value', 'category', 'flags']


def parse_args():
    parser = argparse.ArgumentParser(
        description='Import CTFd challenges and their attachments to a DB from a YAML formated specification file and an associated attachment directory')
    parser.add_argument('--app-root', dest='app_root', type=str,
                        help="app_root directory for the CTFd Flask app (default: 2 directories up from this script)",
                        default=None)
    parser.add_argument('-d', dest='db_uri', type=str, help="URI of the database where the challenges should be stored")
    parser.add_argument('-F', dest='dst_attachments', type=str,
                        help="directory where challenge attachment files should be stored")
    parser.add_argument('-i', dest='in_file', type=str, help="name of the input YAML file (default: export.yaml)",
                        default="export.yaml")
    parser.add_argument('--skip-on-error', dest="exit_on_error", action='store_false',
                        help="If set, the importer will skip the importing challenges which have errors rather than halt.",
                        default=True)
    parser.add_argument('--move', dest="move", action='store_true',
                        help="if set the import proccess will move files rather than copy them", default=False)
    return parser.parse_args()


def process_args(args):
    if not (args.db_uri and args.dst_attachments):
        if args.app_root:
            app.root_path = os.path.abspath(args.app_root)
        else:
            abs_filepath = os.path.abspath(__file__)
            grandparent_dir = os.path.dirname(os.path.dirname(os.path.dirname(abs_filepath)))
            app.root_path = grandparent_dir
        sys.path.append(os.path.dirname(app.root_path))
        app.config.from_object("CTFd.config.Config")

    if args.db_uri:
        app.config['SQLALCHEMY_DATABASE_URI'] = args.db_uri
    if not args.dst_attachments:
        args.dst_attachments = os.path.join(app.root_path, app.config['UPLOAD_FOLDER'])

    return args


class MissingFieldError(Exception):
    def __init__(self, name):
        self.name = value

    def __str__(self):
        return "Error: Missing field '{}'".format(name)


def import_challenges(in_file, dst_attachments, exit_on_error=True, move=False):
    from CTFd.models import db, Challenges, Flags, Tags, Hints, ChallengeFiles
    from CTFd.plugins.dynamic_challenges import DynamicChallenge
    chals = []
    with open(in_file, 'r') as in_stream:
        chals = yaml.safe_load_all(in_stream)

        for chal in chals:
            skip = False
            for req_field in REQ_FIELDS:
                if req_field not in chal:
                    if exit_on_error:
                        raise MissingFieldError(req_field)
                    else:
                        print("Skipping challenge: Missing field '{}'".format(req_field))
                        skip = True
                        break
            if skip:
                continue

            for flag in chal['flags']:
                if 'flag' not in flag:
                    if exit_on_error:
                        raise MissingFieldError('flag')
                    else:
                        print("Skipping flag: Missing field 'flag'")
                        continue
                flag['flag'] = flag['flag'].strip()
                if 'type' not in flag:
                    flag['type'] = "static"

            if 'files' in chal:
                norm_files = []
                for file in chal['files']:
                    # make sure we have only relative paths in the yaml file
                    file = os.path.normpath("/" + file).lstrip('/')
                    # skip files that do not exists
                    if not os.path.exists(os.path.join(os.path.dirname(in_file), file)):
                        print("Skipping file '{}' in challenge '{}': File not found".format(file, chal['name'].strip()))
                        continue
                    else:
                        norm_files.append(file)
                chal['files'] = norm_files

            for hint in chal['hints']:
                if 'type' not in hint:
                    hint['type'] = "standard"

            if chal['type'] == 'dynamic':
                initial = int(chal['value'])
                if 'initial' in chal:
                    initial = int(chal['initial'])

                minimum = 0
                if 'minimum' in chal:
                    minimum = int(chal['minimum'])

                decay = 0
                if 'decay' in chal:
                    decay = int(chal['decay'])

                chal_dbobj = DynamicChallenge(
                    name=chal['name'].strip(),
                    description=chal['description'].strip(),
                    value=int(chal['value']),
                    category=chal['category'].strip(),
                    initial=initial,
                    decay=decay,
                    minimum=minimum
                )
            else:
                # We ignore traling and leading whitespace when importing challenges
                chal_dbobj = Challenges(
                    name=chal['name'].strip(),
                    description=chal['description'].strip(),
                    value=int(chal['value']),
                    category=chal['category'].strip()
                )

            chal_dbobj.state = 'visible'
            if 'hidden' in chal and chal['hidden']:
                if bool(chal['hidden']):
                    chal_dbobj.state = 'hidden'

            chal_dbobj.type = 'standard'
            if 'type' in chal and chal['type']:
                chal_dbobj.type = chal['type']

            matching_chals = Challenges.query.filter_by(
                name=chal_dbobj.name,
                description=chal_dbobj.description,
                value=chal_dbobj.value,
                category=chal_dbobj.category,
                state=chal_dbobj.state,
                type=chal_dbobj.type
            ).all()

            for match in matching_chals:
                if 'tags' in chal:
                    tags_db = [tag.tag for tag in Tags.query.add_columns('tag').filter_by(challenge_id=match.id).all()]
                    if all([tag not in tags_db for tag in chal['tags']]):
                        continue
                if 'files' in chal:
                    files_db = [f.location for f in ChallengeFiles.query.add_columns('location').filter_by(challenge_id=match.id).all()]
                    if len(files_db) != len(chal['files']):
                        continue

                    hashes = []
                    for file_db in files_db:
                        with open(os.path.join(dst_attachments, file_db), 'rb') as f:
                            hash = hashlib.md5(f.read()).digest()
                            hashes.append(hash)

                    mismatch = False
                    for file in chal['files']:
                        filepath = os.path.join(os.path.dirname(in_file), file)
                        with open(filepath, 'rb') as f:
                            hash = hashlib.md5(f.read()).digest()
                            if hash in hashes:
                                hashes.remove(hash)
                            else:
                                mismatch = True
                                break
                    if mismatch:
                        continue

                flags_db = Flags.query.filter_by(challenge_id=match.id).all()
                for flag in chal['flags']:
                    for flag_db in flags_db:
                        if flag['flag'] != flag_db.content:
                            continue
                        if flag['type'] != flag_db.type:
                            continue

                skip = True
                break
            if skip:
                print("Skipping '{}': Duplicate challenge found in DB".format(chal['name'].encode('utf8')))
                continue

            print("Adding {}".format(chal['name'].encode('utf8')))
            db.session.add(chal_dbobj)
            db.session.commit()

            if 'tags' in chal:
                for tag in chal['tags']:
                    tag_dbobj = Tags(chal_dbobj.id, tag)
                    db.session.add(tag_dbobj)

            for flag in chal['flags']:
                flag_db = Flags(challenge_id=chal_dbobj.id, content=flag['flag'], type=flag['type'])
                db.session.add(flag_db)

            for hint in chal['hints']:
                hint_db = Hints(challenge_id=chal_dbobj.id, content=hint['hint'], type=hint['type'],
                                cost=int(hint['cost']))
                db.session.add(hint_db)

            if 'files' in chal:
                for file in chal['files']:
                    filename = os.path.basename(file)
                    dst_filename = secure_filename(filename)

                    dst_dir = None
                    while not dst_dir or os.path.exists(dst_dir):
                        md5hash = hashlib.md5(os.urandom(64)).hexdigest()
                        dst_dir = os.path.join(dst_attachments, md5hash)

                    os.makedirs(dst_dir)
                    dstpath = os.path.join(dst_dir, dst_filename)
                    srcpath = os.path.join(os.path.dirname(in_file), file)

                    if move:
                        shutil.move(srcpath, dstpath)
                    else:
                        shutil.copy(srcpath, dstpath)
                    file_dbobj = ChallengeFiles(challenge_id=chal_dbobj.id,
                                                location=os.path.relpath(dstpath, start=dst_attachments))

                    db.session.add(file_dbobj)
        db.session.commit()

    db.session.close()


if __name__ == "__main__":
    args = parse_args()

    app = Flask(__name__)

    with app.app_context():
        args = process_args(args)
        from CTFd.models import db

        app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
        url = make_url(app.config['SQLALCHEMY_DATABASE_URI'])
        if url.drivername == 'postgres':
            url.drivername = 'postgresql'

        db.init_app(app)

        try:
            if not (url.drivername.startswith('sqlite') or database_exists(url)):
                create_database(url)
            db.create_all()
        except OperationalError:
            db.create_all()
        else:
            db.create_all()

        app.db = db
        import_challenges(args.in_file, args.dst_attachments, args.exit_on_error, move=args.move)