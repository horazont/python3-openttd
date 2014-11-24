``python3-openttd``
===================

``python3-openttd`` is a pure-python client library for interfacing with the
`admin server port <https://wiki.openttd.org/Server_admin_port>`_ of `OpenTTD
<https://www.openttd.org>`_.

Requirements
------------

* `Python <https://www.python.org>`_ 3.4+ (or Python 3.3 with
  `asyncio <https://pypi.python.org/pypi/asyncio>`_ and
  `enum34 <https://pypi.python.org/pypi/enum34>`_)

Basic usage
-----------

See the examples directory for examples :).

Documentation
-------------

Run::

    make docs-html

or::

    cd docs
    make html

to build `sphinx-based <http://sphinx-doc.org/>`_ documentation. View with your
favourite web browser from ``docs/sphinx-data/build/html/index.html`` or run
``make docs-view-html``.
