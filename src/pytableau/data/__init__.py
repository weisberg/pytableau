"""Data layer: ``.hyper`` file management within Tableau workbooks.

Provides the :class:`~pytableau.data.bridge.HyperBridge` which wraps
``tableauhyperapi`` and ``pantab`` behind a unified, ergonomic interface.

Requires the ``[hyper]`` extra::

    pip install "pytableau[hyper]"

.. note::
    Full implementation is tracked in Phase 3 of the development plan.
"""

from __future__ import annotations
