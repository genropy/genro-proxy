Admin UI
========

genro-proxy includes a built-in single-page admin interface.

Overview
--------

The Admin UI is available at ``/ui`` and provides:

- Tenant management (list, add, view)
- Account management per tenant
- Storage management per tenant
- API settings configuration

It requires no build step and uses `Shoelace <https://shoelace.style/>`_ web components.

Accessing the UI
----------------

Start the server and open:

.. code-block:: text

    http://localhost:8000/ui

Features
--------

Tenant Management
^^^^^^^^^^^^^^^^^

- **Sidebar**: Shows all tenants with active/inactive status
- **Add button (+)**: Opens dialog to create new tenant
- **Click tenant**: Shows tenant details and child entities

Account Management
^^^^^^^^^^^^^^^^^^

- **Accounts panel**: Shows accounts for selected tenant
- **Add button (+)**: Opens dialog to add account
- **Click account**: Shows account details and config

Storage Management
^^^^^^^^^^^^^^^^^^

- **Storages panel**: Shows storages for selected tenant
- **Add button (+)**: Opens dialog to add storage
- **Click storage**: Shows storage details and config

API Settings
^^^^^^^^^^^^

Click the gear icon (⚙️) in the header to configure:

- **API Token**: For authenticated access
- **API Base URL**: For remote API connection

Settings are stored in browser localStorage.

Customizing the UI
------------------

The UI is a single HTML file at ``ui/index.html``. To customize:

1. **Copy to your project**:

   .. code-block:: bash

       cp -r /path/to/genro-proxy/ui ./my-proxy/ui

2. **Modify as needed**:

   - Change branding, colors, logos
   - Add domain-specific panels
   - Modify forms for your fields

3. **Override _get_ui_path()** in your ApiManager:

   .. code-block:: python

       class MyApiManager(ApiManager):
           def _get_ui_path(self) -> Path:
               return Path(__file__).parent.parent / "ui"

Adding Custom Panels
--------------------

To add domain-specific UI elements:

1. Edit ``ui/index.html``
2. Add new panel HTML in the main content area
3. Add JavaScript functions for data loading
4. Hook into the render cycle

Example for a mail queue panel:

.. code-block:: html

    <!-- In the lists-container -->
    <div class="list-panel">
        <div class="list-panel-header">
            <h3><sl-icon name="envelope"></sl-icon> Queue</h3>
        </div>
        <div class="list-content" id="queue-list">
            <!-- Populated by JS -->
        </div>
    </div>

.. code-block:: javascript

    // Add load function
    async function loadQueue(tenantId) {
        const res = await apiFetch(`/api/queue/list?tenant_id=${tenantId}`);
        if (res.ok) {
            const json = await res.json();
            queue = json.data || json;
            renderQueueList();
        }
    }

    // Call in selectTenant()
    await loadQueue(tenantId);

Disabling the UI
----------------

To disable the built-in UI:

.. code-block:: python

    class MyApiManager(ApiManager):
        def _get_ui_path(self) -> Path:
            return None  # No UI

Or remove the ui directory from your deployment.

Theming
-------

The UI uses Shoelace components which support theming via CSS custom properties.

To customize colors, add a style block:

.. code-block:: html

    <style>
        :root {
            --sl-color-primary-600: #your-color;
            --sl-color-primary-500: #your-lighter;
        }
    </style>

See `Shoelace theming docs <https://shoelace.style/getting-started/themes>`_
for all available properties.

Mobile Support
--------------

The current UI is designed for desktop use. For mobile-friendly layouts:

1. Add responsive CSS media queries
2. Consider a sidebar toggle for mobile
3. Stack panels vertically on small screens

Security Notes
--------------

The Admin UI:

- Stores API token in browser localStorage
- Sends token in Authorization header
- Should be protected by HTTPS in production
- Can be restricted via network/firewall rules
