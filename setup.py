"""Compatibility metadata for older offline setuptools environments."""

from setuptools import find_packages, setup


setup(
    name="assay-eval",
    version="0.2.0",
    description="Versioned evaluation and deterministic regression gates",
    packages=find_packages("src"),
    package_dir={"": "src"},
    package_data={"assay.web": ["*.html", "*.css", "*.js"]},
    python_requires=">=3.10",
    entry_points={"console_scripts": ["assay=assay.cli:main"]},
)
