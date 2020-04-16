#!/usr/bin/env python

from flask import Flask
from sqlalchemy_utils import database_exists, create_database
from sqlalchemy.engine.url import make_url
from sqlalchemy.exc import OperationalError

# This does in fact rely on being in the CTFd/plugins/*/ folder (3 directories up)
from tarfile import TarFile, TarInfo
from tempfile import TemporaryFile
import yaml
import shutil
import os
import sys
import argparse
import gzip

def parse_args():
    parser = argparse.ArgumentParser(description='Export a DB full of CTFd challenges and theirs attachments into a portable YAML formated specification file and an associated attachment directory')
    parser.add_argument('--app-root', dest='app_root', type=str, help="app_root directory for the CTFd Flask app (default: 2 directories up from this script)", default=None)
    parser.add_argument('-d', dest='db_uri', type=str, help="URI of the database where the challenges are stored")
    parser.add_argument('-F', dest='src_attachments', type=str, help="directory where challenge attachment files are stored")
    parser.add_argument('-o', dest='out_file', type=str, help="name of the output YAML file (default: export.yaml)", default="export.yaml")
    parser.add_argument('-O', dest='dst_attachments', type=str, help="directory for output challenge attachments (default: [OUT_FILENAME].d)", default=None)
    parser.add_argument('--tar', dest='tar', help="if present, output to tar file", action='store_true')
    parser.add_argument('--gz', dest='gz', help="if present, compress the tar file (only used if '--tar' is on)", action='store_true')
    return parser.parse_args()

def process_args(args):
    if not (args.db_uri and args.src_attachments):
        if args.app_root:
            app.root_path = os.path.abspath(args.app_root)
        else:
            abs_filepath = os.path.abspath(__file__)
            grandparent_dir = os.path.dirname(os.path.dirname(os.path.dirname(abs_filepath)))
            app.root_path = grandparent_dir
        sys.path.append(os.path.dirname(app.root_path)) # Enable imports of CTFd modules
        app.config.from_object("CTFd.config.Config")

    if args.db_uri:
        app.config['SQLALCHEMY_DATABASE_URI'] = args.db_uri
    if not args.src_attachments:
        args.src_attachments = os.path.join(app.root_path, app.config['UPLOAD_FOLDER'])
    if not args.dst_attachments:
        args.dst_attachments = args.out_file.rsplit('.', 1)[0]+'.d'

    return args

def copy_files(file_map):
    for src_path, dst_path in file_map.items():
        dst_dir = os.path.dirname(dst_path)
        if not os.path.isdir(dst_dir):
            if os.path.exists(dst_dir):
                raise RuntimeError("Output directory name exists, but is not a directory: %s" % dst_dir)
            os.makedirs(dst_dir)
        shutil.copy(src_path, dst_path)

def tar_files(file_map, tarfile):
    for src_path, dst_path in file_map.items():
        tarfile.add(src_path, dst_path)

def export_challenges(out_file, dst_attachments, src_attachments, tarfile=None):
    from CTFd.models import Challenges, Flags, Tags, Hints, ChallengeFiles
    from CTFd.plugins.dynamic_challenges import DynamicChallenge

    chals = Challenges.query.order_by(Challenges.value).all()
    chals_list = []

    for chal in chals:
        properties = {
            'name': chal.name,
            'value': chal.value,
            'description': chal.description,
            'category': chal.category,
            'type': chal.type
        }

        flags_obj = Flags.query.filter_by(challenge_id=chal.id)
        flags = []
        for flag_obj in flags_obj:
            flag = {'flag': flag_obj.content, 'type': flag_obj.type}
            flags.append(flag)
        properties['flags'] = flags

        hints_obj = Hints.query.filter_by(challenge_id=chal.id)
        hints = []
        for hint_obj in hints_obj:
            hint = {'hint': hint_obj.content, 'type': hint_obj.type, 'cost': hint_obj.cost}
            hints.append(hint)
        properties['hints'] = hints

        if chal.state:
            properties['hidden'] = chal.state == 'hidden'

        tags = [tag.tag for tag in Tags.query.add_columns('value').filter_by(challenge_id=chal.id).all()]
        if tags:
            properties['tags'] = tags

        if chal.type == 'dynamic':
            dynamic_challenge_obj = DynamicChallenge.query.filter_by(id=chal.id).first()
            properties['initial'] = dynamic_challenge_obj.initial
            properties['decay'] = dynamic_challenge_obj.decay
            properties['minimum'] = dynamic_challenge_obj.minimum

        # These file locations will be partial paths in relation to the upload folder
        src_paths_rel = [file.location for file in ChallengeFiles.query.add_columns('location').filter_by(challenge_id=chal.id).all()]

        file_map = {}
        file_list = []
        for src_path_rel in src_paths_rel:
            dirname, filename = os.path.split(src_path_rel)
            dst_dir = os.path.join(dst_attachments, dirname)
            src_path = os.path.join(src_attachments, src_path_rel)
            file_map[src_path] = os.path.join(dst_dir, filename)

            # Create path relative to the output file
            dst_dir_rel = os.path.relpath(dst_dir, start=os.path.dirname(out_file))
            file_list.append(os.path.join(dst_dir_rel, filename))

        if file_map:
            properties['files'] = file_list
            if tarfile:
                tar_files(file_map, tarfile)
            else:
                copy_files(file_map)

        print("Exporting", properties['name'])
        chals_list.append(properties)

    return yaml.safe_dump_all(chals_list, default_flow_style=False, allow_unicode=True, explicit_start=True, sort_keys=False)


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
        from CTFd.models import db

        app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
        db.init_app(app)

        app.db = db

        out_stream.write(export_challenges(args.out_file, args.dst_attachments, args.src_attachments, tarfile))

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