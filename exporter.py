#!/usr/bin/env python2

from flask import Flask
from sqlalchemy_utils import database_exists, create_database
from sqlalchemy.engine.url import make_url
from sqlalchemy.exc import OperationalError

# This does in fact rely on being in the CTFd/plugins/*/ folder (3 directories up)
from tarfile import TarFile, TarInfo
from tempfile import TemporaryFile
import json
import yaml
import shutil
import os
import sys
import argparse
import gzip

def parse_args():
    parser = argparse.ArgumentParser(description='Export a DB full of CTFd challenges and theirs attachments into a portable YAML formated specification file and an associated attachment directory')
    #parser.add_argument('--config', dest='config', type=str, help="module name for a config object. The same as is used for the CTFd flask app. Unused if -d and -F have values (default: ...config.Config)", default="...config.Config")
    parser.add_argument('--app-root', dest='app_root', type=str, help="app_root directory for the CTFd Flask app (default: 2 directories up from this script)", default=None)
    parser.add_argument('-d', dest='db_uri', type=str, help="URI of the database where the challenges are stored")
    parser.add_argument('-F', dest='in_file_dir', type=str, help="directory where challenge attachment files are stored")
    parser.add_argument('-o', dest='out_file', type=str, help="name of the output YAML file (default: export.yaml)", default="export.yaml")
    parser.add_argument('-O', dest='out_file_dir', type=str, help="directory for output challenge attachments (default: export.d)", default="export.d")
    parser.add_argument('--tar', dest='tar', help="if present, output to tar file", action='store_true')
    parser.add_argument('--gz', dest='gz', help="if present, compress the tar file (only used if '--tar' is on)", action='store_true')
    return parser.parse_args()

def process_args(args):
    if not (args.db_uri and args.in_file_dir):
        if args.app_root:
            app.root_path = os.path.abspath(args.app_root)
        else:
            grandparent_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
            app.root_path = grandparent_dir
        sys.path.append(app.root_path)
        app.config.from_object("config.Config")

    if args.db_uri:
        app.config['SQLALCHEMY_DATABASE_URI'] = args.db_uri
    if not args.in_file_dir:
        args.in_file_dir = os.path.join(app.root_path, app.config['UPLOAD_FOLDER'])

    return args

def copy_files(file_map):
    for in_path, out_path in file_map.items():
        out_dir = os.path.dirname(out_path)
        if not os.path.isdir(out_dir):
            if os.path.exists(out_dir):
                raise RuntimeError("Output directory name exists, but is not a directory: %s" % out_dir)
            os.makedirs(out_dir)
        shutil.copy(os.path.join(args.in_file_dir, in_path), out_path) 

def tar_files(file_map, tarfile):
    for in_path, out_path in file_map.items():
        tarfile.add(os.path.join(args.in_file_dir, in_path), out_path) 


def export_challenges(tarfile=None):
    chals = Challenges.query.order_by(Challenges.value).all()
    chals_list = []

    for chal in chals:
        properties = {
        'name': chal.name,
        'value': chal.value,
        'description': chal.description,
        'category': chal.category,
        }
        flags_obj = json.loads(chal.flags)
        flags = []
        for flag in flags_obj:
            if flag['type'] == 0:
                flag.pop('type')
            elif flag['type'] == 1:
                flag['type'] = 'REGEX'
            flags.append(flag)
        properties['flags'] = flags

        if chal.hidden:
            properties['hidden'] = bool(chal.hidden)
        tags = [tag.tag for tag in Tags.query.add_columns('tag').filter_by(chal=chal.id).all()]
        if tags:
            properties['tags'] = tags

        #These file locations will be partial paths in relation to the upload folder
        in_file_paths = [file.location for file in Files.query.add_columns('location').filter_by(chal=chal.id).all()]

        file_map = {}
        file_list = []
        for in_file_path in in_file_paths:
            dirname, filename = os.path.split(in_file_path)
            out_dir = os.path.join(args.out_file_dir, dirname)
            file_map[in_file_path] = os.path.join(out_dir, filename)

            # Create path relative to the output file
            out_dir_rel = os.path.relpath(out_dir, start=os.path.dirname(args.out_file))
            file_list.append(os.path.join(out_dir_rel, filename))

        if file_map:
            properties['files'] = file_list
            if tarfile:
                tar_files(file_map, tarfile)
            else:
                copy_files(file_map)

        print("Exporting", properties['name'])
        chals_list.append(properties)

    return yaml.safe_dump_all(chals_list, default_flow_style=False, allow_unicode=True, explicit_start=True)

if __name__ == "__main__":
    args = parse_args()

    app = Flask(__name__)

    tempfile = None
    tarfile = None
    out_stream = None
    if args.tar:
        out_stream = TemporaryFile(mode='wb+')
        if args.gz:
            tempfile = TemporaryFile(mode='wb+') 
            tarfile = TarFile(fileobj=tempfile, mode='w')
        else:
            tarfile = TarFile(name='export.tar', mode='w')
    else:
        out_stream = open(args.out_file, 'w')


    with app.app_context():
        args = process_args(args)
        from models import db, Challenges, Keys, Tags, Files, DatabaseError

        app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
        db.init_app(app)

        app.db = db

        out_stream.write(export_challenges(tarfile))

    if args.tar:
        print("Tarballing exported files")
        tarinfo = TarInfo(args.out_file) 
        tarinfo.size = out_stream.tell()
        out_stream.seek(0)
        tarfile.addfile(tarinfo, out_stream)
        tarfile.close()

        if args.gz:
            print("Compressing tarball with gzip")
            with gzip.open('export.tar.gz', 'wb') as gz:
                tempfile.seek(0)
                shutil.copyfileobj(tempfile, gz)

    out_stream.close()


