from setuptools import setup, find_packages
import os

def parse_requirements(filename):
    with open(filename, 'r', encoding='utf-8') as f:
        lines = f.read().splitlines()
    return [line for line in lines if line and not line.startswith("#")]

setup(
    name="vietnamese-summarization-nlp",
    version="0.1.0",
    packages=find_packages(),
    install_requires=parse_requirements('requirements.txt'),
    author="Anh Hao",
    description="Đồ án NCKH về Tóm tắt văn bản tiếng Việt đa nền tảng",
    python_requires='>=3.9.25',
)