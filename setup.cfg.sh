#!/bin/bash
VERSION=`PYTHONPATH=src python -c "import dockmaster; print('.'.join(map(str,dockmaster.__version__)))"`
AUTHOR=`PYTHONPATH=src python -c "import dockmaster; print(dockmaster.__author__)"`
AUTHOR_EMAIL=`PYTHONPATH=src python -c "import dockmaster; print(dockmaster.__author_email__)"`
MAINTAINER=`PYTHONPATH=src python -c "import dockmaster; print(dockmaster.__maintainer__)"`
MAINTAINER_EMAIL=`PYTHONPATH=src python -c "import dockmaster; print(dockmaster.__maintainer_email__)"`
DESCRIPTION=`PYTHONPATH=src python -c "import dockmaster; print(dockmaster.__doc__)"`
REQUIRES=`PYTHONPATH=src python -c "list(map(print,['\t'+line.strip() for line in open('requirements.txt', 'r').readlines()]))"`
cat <<EOF > setup.cfg
[metadata]
name = dockmaster
version = ${VERSION}
author = ${AUTHOR}
author_email = ${AUTHOR_EMAIL}
maintainer = ${MAINTAINER}
maintainer_email = ${MAINTAINER_EMAIL}
description = ${DESCRIPTION}
license = Apache License 2.0
url = https://github.com/NicholasGrundl/dockmaster

[options]
packages_dir = 
	=src
packages = find:
include_package_data = True
install_requires =
${REQUIRES}

[options.package_data]
* = *.json, *.yaml, *.csv

[options.packages.find]
where=src

[flake8]
max-line-length = 100

[isort]
multi_line_output = 3
force_single_line = true
include_trailing_comma = true
force_grid_wrap = 0
use_parentheses = true
line_length = 100

[coverage:run]
branch = True
EOF
