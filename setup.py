# -*- coding: utf-8 -*-
from setuptools import setup

packages = \
['sftp_helper']

package_data = \
{'': ['*']}

install_requires = \
['os-helper @ git+https://github.com/warith-harchaoui/os-helper.git@main',
 'pysftp>=0.2.9,<0.3.0']

setup_kwargs = {
    'name': 'sftp-helper',
    'version': '0.1.0',
    'description': 'SFTP Helper is a Python libraty that provides utility function for working with SFTP servers',
    'long_description': '# SFTP Helper\n\n`SFTP Helper` belongs to a collection of libraries called `AI Helpers` developped for building Artificial Intelligence\n\nThis toolbox requires:\n  - a `config.json` for the sftp parameters\n  - that you previously added you SSH key of your local file in the SFTP server\n\n[🕸️ AI Helpers](https://harchaoui.org/warith/ai-helpers)\n\n[![logo](logo.png)](https://harchaoui.org/warith/ai-helpers)\n\nSFTP Helper is a Python library that provides utility function for working with SFTP servers once you specified your SSH Key Credentials.\n\n# Installation\n\n## Install Package\n\nWe can recommand python environments. Check this link if you don\'t know how\n\n[🥸 Tech tips](https://harchaoui.org/warith/4ml/#install)\n\n\n```bash\npip install --force-reinstall --no-cache-dir git+https://github.com/warith-harchaoui/sftp-helper.git@main\n```\n\n## Write your own configuration file\n\nYou have to write your own `sftp_config.json` file or `sftp_config.yaml` file or environment variables (in case you don\'t provide neither `yaml` nor `json` files) or `.env` file:\n\n_JSON_\n```json\n{\n    "sftp_host": "<sftp_host>",\n    "sftp_login": "<sftp_login>",\n    "sftp_passwd": "<sftp_passwd>",\n    "sftp_https": "<sftp_https>",\n    "sftp_destination_path": "<sftp_destination_path>",\n}\n```\nor\n\n_YAML_\n```yaml\nsftp_host: "<sftp_host>"\nsftp_login: "<sftp_login>"\nsftp_passwd: "<sftp_passwd>"\nsftp_https: "<sftp_https>"\nsftp_destination_path: "<sftp_destination_path>"\n```\nor\n\n_ENVIRONMENT VARIABLES_\n```bash\nSFTP_HOST="<sftp_host>" \\\nSFTP_LOGIN="<sftp_login>" \\\nSFTP_PASSWD="<sftp_passwd>" \\\nSFTP_HTTPS="<sftp_https>" \\\nSFTP_DESTINATION_PATH="<sftp_destination_path>" \\\npython <your_python_script>\n```\nor\n\n_.env_\n```\nSFTP_HOST                = <sftp_host>\nSFTP_LOGIN               = <sftp_login>\nSFTP_PASSWD              = <sftp_passwd>\nSFTP_HTTPS               = <sftp_https>\nSFTP_DESTINATION_PATH    = <sftp_destination_path>\n```\n\nIn which you can find these information in your favorite FTP tool (mine is FileZilla):\n  + `<sftp_host>` is the server path `sftp.` ...\n  + `<sftp_login>` and `<sftp_passwd>` that you use in FileZilla\n  + `<sftp_destination_path>` is the remote folder path\n  + `<sftp_https>` corresponds to the web URL of `<sftp_destination_path>`\n  + <your_python_script> is your python script :)\n\n## Usage\n\nHere are an example of how to use SFTP helper **which cannot work without a well written `path/to/sftp_config.json`** :\n```python\nimport sftp_helper as sftph\nimport os_helper as osh\n\n# Write a small text file\nlocal_file = "example.txt"\nwith open(local_file, "wt") as fout:\n    fout.write("A small example of text")\n\ncredentials = sftph.credentials("path/to/sftp_config.json") # or path/to/sftp_config.yaml\n# or nothing in order to fall back on .env or environment variables\n\nremote_file = credentials["sftp_destination_path"] + "/" + local_file\nurl = credentials["sftp_https"] + "/" + local_file\n\nu = sftph.upload(local_file, credentials, remote_file)\n\nosh.check(not(u is None), msg=f\'Upload of {local_file} to {u} failed\')\n\nprint(f"Upload of {local_file} to {u} is successful" if not(u is None) else f"Failed upload of {local_file} to {u}")\n\nurl_exist = osh.is_working_url(url)\n\nprint(f"URL is working:\\n\\t{url}" if url_exist else f"Failed URL:\\n\\t{url}")\n\n```\n\n# Authors\n - [Warith Harchaoui](https://harchaoui.org/warith)\n - [Mohamed Chelali](https://mchelali.github.io)\n - [Bachir Zerroug](https://www.linkedin.com/in/bachirzerroug)\n\n',
    'author': 'Warith Harchaoui',
    'author_email': 'warith.harchaoui@gmail.com>, Mohamed Chelali <mohamed.t.chelali@gmail.com>, Bachir Zerroug <bzerroug@gmail.com',
    'maintainer': 'None',
    'maintainer_email': 'None',
    'url': 'None',
    'packages': packages,
    'package_data': package_data,
    'install_requires': install_requires,
    'python_requires': '>=3.10,<4.0',
}


setup(**setup_kwargs)

