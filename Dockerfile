FROM openmicroscopy/omero-web-standalone:5.27.2

USER root

COPY . /opt/omero/omero-oauth

WORKDIR /opt/omero/omero-oauth

RUN . /opt/omero/web/venv3/bin/activate && python setup.py install

COPY templates/ /opt/omero/web/config/

WORKDIR /opt/setup

USER omero-web
