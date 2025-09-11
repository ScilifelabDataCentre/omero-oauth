FROM openmicroscopy/omero-web-standalone:5.27.2

USER root

COPY . /setup/omero-oauth

RUN . /opt/omero/web/venv3/bin/activate && \
    python -m pip install cffi && \
    cd /setup/omero-oauth && \
    python setup.py install

COPY templates/ /opt/omero/web/config/

USER omero-web
