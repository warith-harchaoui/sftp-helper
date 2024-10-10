from setuptools import setup, find_packages

with open("README.md", "r") as fh:
    long_description = fh.read()
    

setup(
    name="sftp-helper",
    version="1.1.0",
    author="Warith Harchaoui, Mohamed Chelali and Bachir Zerroug",
    author_email="warith.harchaoui@gmail.com", 
    description="SFTP Helper is a Python libraty that provides utility function for working with SFTP servers",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/warith-harchaoui/sftp-helper",
    packages=find_packages(),
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: BSD License",
        "Operating System :: OS Independent",
    ],
    python_requires='>=3.6',
    install_requires=[
        'pysftp',  # Add pysftp for SFTP handling
        'os-helper @ git+ssh://git@github.com/warith-harchaoui/os-helper.git@main'
    ]
)
