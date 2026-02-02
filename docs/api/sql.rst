proxy.sql module
================

Database abstraction layer.

SqlDb
-----

.. autoclass:: proxy.sql.sqldb.SqlDb
   :members:
   :undoc-members:
   :show-inheritance:

Table
-----

.. autoclass:: proxy.sql.table.Table
   :members:
   :undoc-members:
   :show-inheritance:

Column Types
------------

.. autoclass:: proxy.sql.column.Column
   :members:
   :undoc-members:

.. autoclass:: proxy.sql.column.ColumnManager
   :members:
   :undoc-members:

Type aliases for column definitions:

- ``String`` - TEXT column
- ``Integer`` - INTEGER column
- ``Timestamp`` - TIMESTAMP column

Adapters
--------

SQLiteAdapter
^^^^^^^^^^^^^

.. autoclass:: proxy.sql.adapters.sqlite.SQLiteAdapter
   :members:
   :undoc-members:
   :show-inheritance:

PostgreSQLAdapter
^^^^^^^^^^^^^^^^^

.. autoclass:: proxy.sql.adapters.postgresql.PostgreSQLAdapter
   :members:
   :undoc-members:
   :show-inheritance:
