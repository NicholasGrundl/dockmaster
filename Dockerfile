####### Core OS build layer
FROM ubuntu:20.04 AS os-base
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y \
    wget \
    bzip2 \
    ca-certificates \
    curl \
    && rm -rf /var/lib/apt/lists/*

# --- Install Miniconda
ENV MINICONDA_VERSION=4.9.2
ENV CONDA_DIR=/opt/conda
RUN wget --quiet https://repo.anaconda.com/miniconda/Miniconda3-py39_${MINICONDA_VERSION}-Linux-x86_64.sh -O ~/miniconda.sh && \
    /bin/bash ~/miniconda.sh -b -p ${CONDA_DIR} && \
    rm ~/miniconda.sh
ENV PATH=${CONDA_DIR}/bin:${PATH}

####### Core Python build layer
FROM os-base AS python-base
ENV PYTHON_VERSION=3.10
RUN conda create -n myapp-backend python=${PYTHON_VERSION} pip -y
ENV CONDA_DEFAULT_ENV=myapp-backend
ENV PATH=${CONDA_DIR}/envs/${CONDA_DEFAULT_ENV}/bin:${PATH}
COPY requirements.txt /tmp/requirements.txt
RUN pip install -r /tmp/requirements.txt && \
    conda clean -afy && \
    find ${CONDA_DIR} -follow -type f -name '*.a' -delete && \
    find ${CONDA_DIR} -follow -type f -name '*.pyc' -delete && \
    find ${CONDA_DIR} -follow -type f -name '*.js.map' -delete

####### App build layer
FROM python-base AS app-build
WORKDIR /app
COPY ./src/dockmaster /app/dockmaster
# -- build local package/app if needed
# RUN pip install --no-cache-dir . && \
#     find /app -type d -name "__pycache__" -exec rm -rf {} +
RUN find /app -type d -name "__pycache__" -exec rm -rf {} +


####### Final backend run layer
FROM python-base AS runtime
WORKDIR /app
COPY --from=app-build /app /app
COPY --from=app-build ${CONDA_DIR}/envs/${CONDA_DEFAULT_ENV} ${CONDA_DIR}/envs/${CONDA_DEFAULT_ENV}
ENV PATH=${CONDA_DIR}/envs/${CONDA_DEFAULT_ENV}/bin:${PATH}

# Create a non-root user to run the application
RUN useradd -m myapp && \
    chown -R myapp:myapp /app
USER myapp

EXPOSE 8001
CMD ["python", "-m", "uvicorn", "dockmaster.main:app", "--host", "0.0.0.0", "--port", "8001"]