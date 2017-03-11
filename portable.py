from flask import Blueprint, send_file
from exporter import export_challenges
from importer import import_challenges
from tempfile import TemporaryFile
from tarfile import TarFile, TarInfo
from gzip import GzipFile
from CTFd.utils import admins_only
import gzip
import os
import shutil

def load(app):
    #sys.path.append(os.path.dirname(app.root_path)) # Enable imports of CTFd modules

    portable = Blueprint('portable', __name__)

    @portable.route('/admin/yaml', methods=['GET'])
    @admins_only
    def export_yaml():
        tarfile_backend = TemporaryFile(mode='wb+')
        yamlfile = TemporaryFile(mode='wb+')
        tarfile = TarFile(fileobj=tarfile_backend, mode='w')
        src_attachments = os.path.join(app.root_path, app.config['UPLOAD_FOLDER'])
        print(src_attachments)

        yamlfile.write(export_challenges('export.yaml', 'export.d', src_attachments, tarfile))

        tarinfo = TarInfo('export.yaml')
        tarinfo.size = yamlfile.tell()
        yamlfile.seek(0)
        tarfile.addfile(tarinfo, yamlfile)
        tarfile.close()
        yamlfile.close()
        

        gzipfile_backend = TemporaryFile(mode='wb+')
        gzipfile = GzipFile(fileobj=gzipfile_backend)

        tarfile_backend.seek(0)
        shutil.copyfileobj(tarfile_backend, gzipfile)

        tarfile_backend.close()
        gzipfile.close()
        gzipfile_backend.seek(0)
        return send_file(gzipfile_backend, as_attachment=True, attachment_filename='export.tar.gz')

    app.register_blueprint(portable)
