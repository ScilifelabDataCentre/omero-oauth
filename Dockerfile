FROM openmicroscopy/omero-web-standalone:5.29.0

USER root

COPY . /setup/omero-oauth

RUN . /opt/omero/web/venv3/bin/activate && \
    python -m pip install cffi && \
    python -m pip install omero-openlink==2.1.3 && \
    cd /setup/omero-oauth && \
    python -m pip install .

COPY templates/ /opt/omero/web/config/

USER omero-web