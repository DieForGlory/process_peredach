from flask import Blueprint

cadastre_bp = Blueprint(
    'cadastre_process',
    __name__,
    template_folder='templates',
)

from . import routes