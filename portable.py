from flask import Blueprint, send_file, request, abort, render_template_string
from werkzeug.utils import secure_filename
from .exporter import export_challenges
from .importer import import_challenges
from tempfile import TemporaryFile, mkdtemp
from gzip import GzipFile
from CTFd.utils.decorators import admins_only
import tarfile
import gzip
import os
import shutil


def load(app):
    portable = Blueprint('portable', __name__)

    @portable.route('/admin/yaml', methods=['GET', 'POST'])
    @admins_only
    def transfer_yaml():
        upload_folder = os.path.join(app.root_path, app.config['UPLOAD_FOLDER'])
        if request.method == 'GET':
            tarfile_backend = TemporaryFile(mode='wb+')
            yamlfile = TemporaryFile(mode='wb+')
            tarball = tarfile.open(fileobj=tarfile_backend, mode='w')

            yamlfile.write(bytes(export_challenges('export.yaml', 'export.d', upload_folder, tarball), "UTF-8"))

            tarinfo = tarfile.TarInfo('export.yaml')
            tarinfo.size = yamlfile.tell()
            yamlfile.seek(0)
            tarball.addfile(tarinfo, yamlfile)
            tarball.close()
            yamlfile.close()


            gzipfile_backend = TemporaryFile(mode='wb+')
            gzipfile = GzipFile(fileobj=gzipfile_backend, mode='wb')

            tarfile_backend.seek(0)
            shutil.copyfileobj(tarfile_backend, gzipfile)

            tarfile_backend.close()
            gzipfile.close()
            gzipfile_backend.seek(0)
            return send_file(gzipfile_backend, as_attachment=True, attachment_filename='export.tar.gz')

        if request.method == 'POST':
            if 'file' not in request.files:
                abort(400)

            file = request.files['file']

            readmode = 'r:gz'
            if file.filename.endswith('.tar'):
                readmode = 'r'
            if file.filename.endswith('.bz2'):
                readmode = 'r:bz2'

            tempdir = mkdtemp()
            try:
                archive = tarfile.open(fileobj=file.stream, mode=readmode)

                if 'export.yaml' not in archive.getnames():
                    shutil.rmtree(tempdir)
                    abort(400)

                # Check for attempts to escape to higher dirs
                for member in archive.getmembers():
                    memberpath = os.path.normpath(member.name)
                    if memberpath.startswith('/') or '..' in memberpath.split('/'):
                        shutil.rmtree(tempdir)
                        abort(400)

                    if member.linkname:
                        linkpath = os.path.normpath(member.linkname)
                        if linkpath.startswith('/') or '..' in linkpath.split('/'):
                            shutil.rmtree(tempdir)
                            abort(400)


                archive.extractall(path=tempdir)

            except tarfile.TarError:
                shutil.rmtree(tempdir)
                print('b')
                abort(400)

            in_file = os.path.join(tempdir, 'export.yaml')
            import_challenges(in_file, upload_folder, move=True)

            shutil.rmtree(tempdir)

            return '1'

    @portable.route('/admin/transfer', methods=['GET'])
    @admins_only
    def yaml_form():
        templatepath = os.path.abspath(os.path.join(os.path.dirname(__file__), 'transfer.html'))
        with open(templatepath, 'r') as templatefile:
            return render_template_string(templatefile.read())

    app.register_blueprint(portable)
