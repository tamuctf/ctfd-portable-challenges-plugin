#!/usr/bin/env python2

from flask import Flask
from sqlalchemy_utils import database_exists, create_database
from sqlalchemy.engine.url import make_url
from sqlalchemy.exc import OperationalError
from werkzeug.utils import secure_filename

import json
import hashlib
import yaml
import shutil
import os
import sys
import hashlib
import argparse

def parse_args():
    parser = argparse.ArgumentParser(description='Import CTFd challenges and their attachments to a DB from a YAML formated specification file and an associated attachment directory')
    parser.add_argument('--app-root', dest='app_root', type=str, help="app_root directory for the CTFd Flask app (default: 2 directories up from this script)", default=None)
    parser.add_argument('-d', dest='db_uri', type=str, help="URI of the database where the challenges should be stored")
    parser.add_argument('-F', dest='out_file_dir', type=str, help="directory where challenge attachment files should be stored")
    parser.add_argument('-i', dest='in_file', type=str, help="name of the input YAML file (default: export.yaml)", default="export.yaml")
    parser.add_argument('--skip-on-error', dest="exit_on_error", action='store_false', help="If set, the importer will skip the importing challenges which have errors rather than halt.", default=True)
    return parser.parse_args()

def process_args(args):
    if not (args.db_uri and args.out_file_dir):
        if args.app_root:
            app.root_path = os.path.abspath(args.app_root)
        else:
            abs_filepath = os.path.abspath(__file__)
            grandparent_dir = os.path.dirname(os.path.dirname(os.path.dirname(abs_filepath)))
            app.root_path = grandparent_dir
        sys.path.append(app.root_path)
        app.config.from_object("config.Config")

    if args.db_uri:
        app.config['SQLALCHEMY_DATABASE_URI'] = args.db_uri
    if not args.out_file_dir:
        args.out_file_dir = os.path.join(app.root_path, app.config['UPLOAD_FOLDER'])

    return args

class MissingFieldError(Exception):
    def __init__(self, name):
        self.name = value
    def __str__(self):
        return "Error: Missing field '{}'".format(name)

if __name__ == "__main__":
    args = parse_args()
    
    app = Flask(__name__)

    req_fields = ['name', 'description', 'value', 'category', 'flags']

    with app.app_context():
        args = process_args(args)
        from models import db, Challenges, Keys, Tags, Files, DatabaseError

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

        chals = []
        with open(args.in_file, 'r') as in_stream:
            chals = yaml.safe_load_all(in_stream)

            for chal in chals:
                skip = False
                for req_field in req_fields:
                    if req_field not in chal:
                        if args.exit_on_error:
                            raise MissingFieldError(req_field)
                        else:
                            print "Skipping challenge: Missing field '{}'".format(req_field)
                            skip = True
                            break
                if skip:
                    continue

                for flag in chal['flags']:
                    if 'flag' not in flag:
                        if args.exit_on_error:
                            raise MissingFieldError('flag')
                        else:
                            print "Skipping flag: Missing field 'flag'"
                            continue
                    if 'type' in flag == "REGEX":
                        flag['type'] = 1
                    else:
                        flag['type'] = 0

                chal_dbobj = Challenges(
                    chal['name'],
                    chal['description'],
                    chal['value'],
                    chal['category'],
                    chal['flags']
                )

                if 'hidden' in chal and chal['hidden']:
                    chal_dbobj.hidden = True

                matching_chals = Challenges.query.filter_by(
                    name=chal_dbobj.name,
                    description=chal_dbobj.description,
                    value=chal_dbobj.value,
                    category=chal_dbobj.category,
                    hidden=chal_dbobj.hidden
                ).all()

                for match in matching_chals:
                    if 'tags' in chal:
                        tags_db = [tag.tag for tag in Tags.query.add_columns('tag').filter_by(chal=match.id).all()]
                        if all([tag not in tags_db for tag in chal['tags']]):
                            continue
                    if 'files' in chal:
                        files_db = [f.location for f in Files.query.add_columns('location').filter_by(chal=match.id).all()]
                        if len(files_db) != len(chal['files']):
                            continue

                        hashes = []
                        for file_db in files_db:
                            with open(os.path.join(args.out_file_dir, file_db), 'r') as f:
                                hash = hashlib.md5(f.read()).digest()
                                hashes.append(hash)

                        mismatch = False
                        for file in chal['files']:
                            filepath = os.path.join(os.path.dirname(args.in_file), file)
                            with open(filepath, 'r') as f:
                                hash = hashlib.md5(f.read()).digest()
                                if hash in hashes:
                                    hashes.remove(hash)
                                else:
                                    mismatch = True
                                    break
                        if mismatch:
                            continue

                    if json.loads(match.flags) == chal['flags']:
                        skip = True
                        break
                if skip:
                    print "Skipping {}: Duplicate challenge found in DB".format(chal['name'].encode('utf8'))
                    continue

                print "Adding {}".format(chal['name'].encode('utf8'))
                db.session.add(chal_dbobj)
                db.session.commit()

                if 'tags' in chal:
                    for tag in chal['tags']:
                        tag_dbobj = Tags(chal_dbobj.id, tag)
                        db.session.add(tag_dbobj)

                if 'files' in chal:
                    for file in chal['files']:
                        filename = os.path.basename(file)
                        dstfilename = secure_filename(filename)

                        md5hash = hashlib.md5(os.urandom(64)).hexdigest()
                        dstdir = os.path.join(args.out_file_dir, md5hash)

                        while os.path.exists(dstdir):
                            md5hash = hashlib.md5(os.urandom(64)).hexdigest()
                            dstdir = os.path.join(file_dir, md5hash)

                        os.makedirs(dstdir)
                        dstpath = os.path.join(dstdir, dstfilename)
                        srcpath = os.path.join(os.path.dirname(args.in_file), file)

                        shutil.copy(srcpath, dstpath)
                        file_dbobj = Files(chal_dbobj.id, os.path.relpath(dstpath, start=args.out_file_dir))

                        db.session.add(file_dbobj)

        db.session.commit()
        db.session.close()
