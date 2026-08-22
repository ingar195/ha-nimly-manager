import {
    LitElement,
    html,
    css,
} from "https://unpkg.com/lit-element@2.4.0/lit-element.js?module";

class NimlykoderPanel extends LitElement {
    static get properties() {
        return {
            hass: { type: Object },
            narrow: { type: Boolean },
            route: { type: Object },
            panel: { type: Object },
            codes: { type: Array },
            loading: { type: Boolean },
            error: { type: String },
            searchQuery: { type: String },
            showAddDialog: { type: Boolean },
            showEditDialog: { type: Boolean },
            showRemoveDialog: { type: Boolean },
            showPinConfirmDialog: { type: Boolean },
            editingCode: { type: Object },
            editFormError: { type: String },
            removingCode: { type: Object },
            config: { type: Object },
            showExpiredInfo: { type: Boolean },
            suggestedSlot: { type: Number },
            translations: { type: Object },
            pendingPinUpdate: { type: Object },
            // Auto-lock
            autoLockEnabled: { type: Boolean },
            autoLockDelay: { type: Number },
            showAutoLockDialog: { type: Boolean },
            // Door sensor
            doorSensorEntity: { type: String },
            // Battery
            batteryEntity: { type: String },
            // Lock device settings
            showLockSettingsDialog: { type: Boolean },
            lockSettings: { type: Object },
            lockSettingsLoading: { type: Boolean },
            lockSettingsError: { type: String },
            lockSettingsSaving: { type: Boolean },
            // Logbook
            logbookEntries: { type: Array },
            logbookLoading: { type: Boolean },
        };
    }

    constructor() {
        super();
        this.codes = [];
        this.loading = true;
        this.error = null;
        this.searchQuery = "";
        this.showAddDialog = false;
        this.showEditDialog = false;
        this.showRemoveDialog = false;
        this.showPinConfirmDialog = false;
        this.editingCode = null;
        this.editFormError = null;
        this.removingCode = null;
        this.config = { auto_expire: true, cleanup_time: "03:00:00" };
        this.showExpiredInfo = false;
        this.suggestedSlot = null;
        this.translations = this._defaultTranslations();
        this.pendingPinUpdate = null;
        // Auto-lock
        this.autoLockEnabled = false;
        this.autoLockDelay = 300;
        this.showAutoLockDialog = false;
        // Door sensor
        this.doorSensorEntity = null;
        // Battery
        this.batteryEntity = null;
        // Lock device settings
        this.showLockSettingsDialog = false;
        this.lockSettings = null;
        this.lockSettingsLoading = false;
        this.lockSettingsError = null;
        this.lockSettingsSaving = false;
        // Logbook
        this.logbookEntries = [];
        this.logbookLoading = false;
    }

    // Default English translations (fallback)
    _defaultTranslations() {
        return {
            title: "Nimlykoder",
            subtitle: "Manage PIN codes for your Nimly lock",
            add_code: "Add Code",
            search_placeholder: "Search by name, slot, or type...",
            stats: {
                total: "Total Codes",
                permanent: "Permanent",
                guest: "Guest",
                expired: "Expired",
            },
            status: {
                active: "Active",
                expired: "Expired",
                reserved: "Reserved",
            },
            type: {
                permanent: "Permanent",
                guest: "Guest",
            },
            dialog: {
                add_title: "Add New Person",
                edit_title: "Edit Person",
                remove_title: "Remove Person",
                confirm_remove: "Are you sure you want to remove",
                remove_description: "This will delete the PIN code from slot {slot} and remove it from the lock.",
                name: "Name",
                name_placeholder: "e.g., John Doe",
                pin_code: "PIN Code",
                pin_placeholder: "4-6 digits",
                pin_hint: "Enter a 4-6 digit PIN code",
                change_pin: "Change PIN Code",
                pin_change_warning: "Leave empty to keep the current PIN code",
                confirm_pin_change: "Confirm PIN Change",
                pin_warning_title: "Warning: Irreversible Action",
                pin_warning_message: "Changing the PIN code will permanently replace the old code. There is no way to retrieve the previous PIN code.",
                pin_confirm_question: "Are you sure you want to change the PIN code for {name}?",
                confirm_change: "Yes, Change PIN",
                type: "Type",
                expiry: "Expiry Date",
                expiry_hint: "Leave empty for no expiry (permanent access)",
                permanent_no_expiry: "Permanent codes do not have an expiry date.",
                slot: "Slot",
                next_available: "Next available",
                cancel: "Cancel",
                save: "Save Changes",
                add: "Add Person",
                remove: "Remove",
            },
            errors: {
                name_required: "Name is required",
                pin_invalid: "PIN code must be 4-6 digits",
            },
            empty: {
                title: "No PIN codes yet",
                description: "Add your first person to get started with Nimlykoder",
                add_first: "Add First Person",
            },
            no_results: {
                title: "No results found",
                description: "Try a different search term",
            },
            loading: "Loading codes...",
            retry: "Retry",
            expires: "Expires",
            expired_on: "Expired",
            slot_label: "Slot",
            expired_info: {
                title: "Expired Codes",
                description: "Expired codes have passed their set expiry date and are no longer valid for entry.",
                auto_cleanup: "Auto-cleanup is enabled. Expired codes will be automatically removed at {time}.",
                manual_cleanup: "Auto-cleanup is disabled. Remove expired codes manually.",
            },
        };
    }

    static get styles() {
        return css`
            :host {
                display: block;
                --primary-color: var(--ha-primary-color, #03a9f4);
                --text-primary: var(--primary-text-color, #212121);
                --text-secondary: var(--secondary-text-color, #727272);
                --divider: var(--divider-color, #e0e0e0);
                --card-bg: var(--card-background-color, #fff);
                --bg: var(--primary-background-color, #fafafa);
            }

            /* Top App Bar */
            .app-header {
                background-color: var(--app-header-background-color, var(--primary-color));
                color: var(--app-header-text-color, var(--text-primary-color, #fff));
                display: flex;
                align-items: center;
                height: 56px;
                padding: 0 4px;
                box-sizing: border-box;
                position: sticky;
                top: 0;
                z-index: 4;
            }

            .menu-btn {
                width: 48px;
                height: 48px;
                display: flex;
                align-items: center;
                justify-content: center;
                background: none;
                border: none;
                cursor: pointer;
                color: inherit;
                border-radius: 50%;
                margin: 0 4px;
            }

            .menu-btn:hover {
                background: rgba(255, 255, 255, 0.1);
            }

            .menu-btn svg {
                width: 24px;
                height: 24px;
            }

            .app-header-title {
                font-size: 20px;
                font-weight: 400;
                margin-left: 8px;
                flex: 1;
            }

            .header-actions {
                display: flex;
                align-items: center;
                gap: 4px;
                margin-right: 4px;
            }

            .auto-lock-badge {
                display: flex;
                align-items: center;
                gap: 4px;
                padding: 4px 10px;
                border-radius: 12px;
                font-size: 12px;
                font-weight: 500;
                background: rgba(255,255,255,0.2);
                cursor: pointer;
                white-space: nowrap;
            }

            .auto-lock-badge.active {
                background: rgba(76, 175, 80, 0.35);
            }

            .auto-lock-badge svg {
                width: 16px;
                height: 16px;
            }

            .container {
                max-width: 1200px;
                margin: 0 auto;
                padding: 16px;
            }

            /* Lock Status Bar */
            .lock-status-bar {
                display: flex;
                align-items: center;
                gap: 12px;
                padding: 12px 16px;
                background: var(--card-bg);
                border-radius: 12px;
                margin-bottom: 20px;
                box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
            }

            .lock-status-icon {
                width: 40px;
                height: 40px;
                border-radius: 50%;
                display: flex;
                align-items: center;
                justify-content: center;
                flex-shrink: 0;
            }

            .lock-status-icon.locked {
                background: rgba(76, 175, 80, 0.15);
                color: #4caf50;
            }

            .lock-status-icon.unlocked {
                background: rgba(255, 152, 0, 0.15);
                color: #ff9800;
            }

            .lock-status-icon.unknown {
                background: rgba(158, 158, 158, 0.15);
                color: #9e9e9e;
            }

            .lock-status-icon svg {
                width: 24px;
                height: 24px;
            }

            .lock-status-info {
                flex: 1;
                min-width: 0;
            }

            .lock-status-name {
                font-size: 16px;
                font-weight: 500;
                color: var(--text-primary);
                white-space: nowrap;
                overflow: hidden;
                text-overflow: ellipsis;
            }

            .lock-status-state {
                font-size: 13px;
                color: var(--text-secondary);
                display: flex;
                align-items: center;
                gap: 6px;
            }

            .lock-status-state .dot {
                width: 8px;
                height: 8px;
                border-radius: 50%;
            }

            .lock-status-state .dot.locked { background: #4caf50; }
            .lock-status-state .dot.unlocked { background: #ff9800; }
            .lock-status-state .dot.unknown { background: #9e9e9e; }

            .lock-status-slots {
                text-align: right;
                flex-shrink: 0;
            }

            .lock-status-slots-count {
                font-size: 20px;
                font-weight: 600;
                color: var(--primary-color);
            }

            .lock-status-slots-label {
                font-size: 11px;
                color: var(--text-secondary);
                text-transform: uppercase;
                letter-spacing: 0.5px;
            }

            /* Search and Actions Bar */
            .toolbar {
                display: flex;
                gap: 12px;
                margin-bottom: 20px;
                flex-wrap: wrap;
            }

            .search-container {
                flex: 1;
                min-width: 200px;
                position: relative;
            }

            .search-input {
                width: 100%;
                padding: 12px 16px 12px 44px;
                border: 1px solid var(--divider);
                border-radius: 28px;
                font-size: 16px;
                background: var(--card-bg);
                color: var(--text-primary);
                outline: none;
                transition: border-color 0.2s, box-shadow 0.2s;
                box-sizing: border-box;
            }

            .search-input:focus {
                border-color: var(--primary-color);
                box-shadow: 0 0 0 1px var(--primary-color);
            }

            .search-input::placeholder { color: var(--text-secondary); }

            .search-icon {
                position: absolute;
                left: 16px;
                top: 50%;
                transform: translateY(-50%);
                color: var(--text-secondary);
                pointer-events: none;
            }

            /* Buttons */
            .btn {
                display: inline-flex;
                align-items: center;
                gap: 8px;
                padding: 12px 24px;
                border: none;
                border-radius: 28px;
                font-size: 14px;
                font-weight: 500;
                cursor: pointer;
                transition: all 0.2s;
                text-transform: uppercase;
                letter-spacing: 0.5px;
            }

            .btn-primary {
                background: var(--primary-color);
                color: var(--text-primary-color, white);
                box-shadow: 0 2px 8px rgba(var(--rgb-primary-color, 3, 169, 244), 0.4);
            }

            .btn-primary:hover {
                filter: brightness(1.1);
                box-shadow: 0 4px 16px rgba(var(--rgb-primary-color, 3, 169, 244), 0.5);
                transform: translateY(-1px);
            }

            .btn-secondary {
                background: var(--card-bg);
                color: var(--text-primary);
                border: 1px solid var(--divider);
            }

            .btn-secondary:hover { background: var(--bg); }

            .btn-danger {
                background: #f44336;
                color: white;
            }

            .btn-danger:hover { background: #d32f2f; }

            .btn-text {
                background: transparent;
                color: var(--primary-color);
                padding: 8px 16px;
            }

            .btn-text:hover { background: rgba(3, 169, 244, 0.1); }

            .btn-icon {
                width: 40px;
                height: 40px;
                padding: 0;
                border-radius: 50%;
                justify-content: center;
            }

            .btn svg {
                width: 20px;
                height: 20px;
                flex-shrink: 0;
            }

            /* Stats Cards */
            .stats {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
                gap: 16px;
                margin-bottom: 24px;
            }

            .stat-card {
                background: var(--card-bg);
                border-radius: 16px;
                padding: 20px;
                text-align: center;
                box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
            }

            .stat-value {
                font-size: 32px;
                font-weight: 600;
                color: var(--text-primary);
            }

            .stat-label {
                font-size: 13px;
                color: var(--text-secondary);
                margin-top: 4px;
                text-transform: uppercase;
                letter-spacing: 0.5px;
            }

            .stat-header {
                display: flex;
                align-items: center;
                justify-content: center;
                gap: 8px;
            }

            .info-icon {
                width: 20px;
                height: 20px;
                color: var(--text-secondary);
                cursor: pointer;
                transition: color 0.2s;
            }

            .info-icon:hover { color: var(--primary-color); }

            .stat-card.expired { position: relative; }

            .info-tooltip {
                position: absolute;
                bottom: calc(100% + 12px);
                left: 50%;
                transform: translateX(-50%);
                background: var(--card-bg);
                border: 1px solid var(--divider);
                border-radius: 12px;
                padding: 16px;
                width: 280px;
                box-shadow: 0 4px 20px rgba(0, 0, 0, 0.15);
                z-index: 100;
                text-align: left;
            }

            .info-tooltip::after {
                content: '';
                position: absolute;
                top: 100%;
                left: 50%;
                transform: translateX(-50%);
                border: 8px solid transparent;
                border-top-color: var(--card-bg);
            }

            .info-tooltip::before {
                content: '';
                position: absolute;
                top: 100%;
                left: 50%;
                transform: translateX(-50%);
                border: 9px solid transparent;
                border-top-color: var(--divider);
            }

            .info-tooltip h4 {
                margin: 0 0 8px 0;
                font-size: 14px;
                font-weight: 600;
                color: var(--text-primary);
                display: flex;
                align-items: center;
                gap: 8px;
            }

            .info-tooltip h4 svg {
                width: 18px;
                height: 18px;
                color: #f44336;
            }

            .info-tooltip p {
                margin: 0;
                font-size: 13px;
                color: var(--text-secondary);
                line-height: 1.5;
            }

            .info-tooltip .highlight {
                color: var(--primary-color);
                font-weight: 500;
            }

            .stat-card.permanent .stat-value { color: #4caf50; }
            .stat-card.guest .stat-value { color: #2196f3; }
            .stat-card.expired .stat-value { color: #f44336; }

            /* Person List */
            .person-list { display: grid; gap: 12px; }

            .person-card {
                background: var(--card-bg);
                border-radius: 16px;
                padding: 16px 20px;
                display: flex;
                align-items: center;
                gap: 16px;
                box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
                transition: box-shadow 0.2s, transform 0.2s;
            }

            .person-card:hover { box-shadow: 0 4px 16px rgba(0, 0, 0, 0.1); }

            .person-avatar {
                width: 52px;
                height: 52px;
                border-radius: 50%;
                display: flex;
                align-items: center;
                justify-content: center;
                font-size: 20px;
                font-weight: 600;
                color: white;
                flex-shrink: 0;
            }

            .avatar-permanent { background: linear-gradient(135deg, #4caf50 0%, #2e7d32 100%); }
            .avatar-guest { background: linear-gradient(135deg, #2196f3 0%, #1565c0 100%); }
            .avatar-expired { background: linear-gradient(135deg, #9e9e9e 0%, #616161 100%); }

            .person-info { flex: 1; min-width: 0; }

            .person-name {
                font-size: 16px;
                font-weight: 500;
                color: var(--text-primary);
                margin: 0 0 4px 0;
                white-space: nowrap;
                overflow: hidden;
                text-overflow: ellipsis;
            }

            .person-details { display: flex; gap: 16px; flex-wrap: wrap; }

            .person-detail {
                display: flex;
                align-items: center;
                gap: 4px;
                font-size: 13px;
                color: var(--text-secondary);
            }

            .person-detail svg { width: 16px; height: 16px; opacity: 0.7; }

            .badge {
                padding: 4px 12px;
                border-radius: 12px;
                font-size: 12px;
                font-weight: 500;
                text-transform: uppercase;
                letter-spacing: 0.5px;
            }

            .badge-permanent { background: #e8f5e9; color: #2e7d32; }
            .badge-guest { background: #e3f2fd; color: #1565c0; }
            .badge-expired { background: #ffebee; color: #c62828; }

            .person-actions { display: flex; gap: 8px; }

            /* Empty State */
            .empty-state {
                text-align: center;
                padding: 60px 20px;
                background: var(--card-bg);
                border-radius: 16px;
                box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
            }

            .empty-icon {
                width: 80px;
                height: 80px;
                margin: 0 auto 20px;
                background: var(--primary-color);
                border-radius: 50%;
                display: flex;
                align-items: center;
                justify-content: center;
                color: white;
            }

            .empty-icon svg { width: 40px; height: 40px; }

            .empty-state h2 {
                margin: 0 0 8px 0;
                font-size: 20px;
                font-weight: 500;
                color: var(--text-primary);
            }

            .empty-state p { margin: 0 0 24px 0; color: var(--text-secondary); }

            /* Loading */
            .loading-container { text-align: center; padding: 60px 20px; }

            .spinner {
                width: 48px;
                height: 48px;
                border: 3px solid var(--divider);
                border-top-color: var(--primary-color);
                border-radius: 50%;
                animation: spin 1s linear infinite;
                margin: 0 auto 16px;
            }

            .spinner-sm {
                width: 24px;
                height: 24px;
                border-width: 2px;
                margin: 12px auto;
            }

            @keyframes spin { to { transform: rotate(360deg); } }

            /* Error */
            .error-banner {
                background: #ffebee;
                color: #c62828;
                padding: 12px 16px;
                border-radius: 8px;
                margin-bottom: 16px;
                display: flex;
                align-items: center;
                gap: 12px;
            }

            .error-banner svg { width: 24px; height: 24px; flex-shrink: 0; }
            .error-banner span { flex: 1; }

            /* Dialog Overlay */
            .dialog-overlay {
                position: fixed;
                top: 0;
                left: 0;
                right: 0;
                bottom: 0;
                background: rgba(0, 0, 0, 0.5);
                display: flex;
                align-items: center;
                justify-content: center;
                z-index: 1000;
                padding: 16px;
            }

            .dialog {
                background: var(--card-bg);
                border-radius: 16px;
                width: 100%;
                max-width: 480px;
                max-height: 90vh;
                overflow: auto;
                box-shadow: 0 8px 32px rgba(0, 0, 0, 0.2);
            }

            .dialog-header {
                padding: 20px 24px;
                border-bottom: 1px solid var(--divider);
                display: flex;
                align-items: center;
                justify-content: space-between;
            }

            .dialog-header h2 { margin: 0; font-size: 20px; font-weight: 500; }

            .dialog-content { padding: 24px; }

            .dialog-actions {
                padding: 16px 24px;
                border-top: 1px solid var(--divider);
                display: flex;
                justify-content: flex-end;
                gap: 12px;
            }

            /* Form */
            .form-group { margin-bottom: 20px; }

            .form-group label {
                display: block;
                margin-bottom: 8px;
                font-size: 14px;
                font-weight: 500;
                color: var(--text-primary);
            }

            .form-group input,
            .form-group select {
                width: 100%;
                padding: 12px 16px;
                border: 1px solid var(--divider);
                border-radius: 8px;
                font-size: 16px;
                background: var(--bg);
                color: var(--text-primary);
                outline: none;
                transition: border-color 0.2s;
                box-sizing: border-box;
            }

            .form-group input:focus,
            .form-group select:focus { border-color: var(--primary-color); }

            .form-group small {
                display: block;
                margin-top: 6px;
                font-size: 12px;
                color: var(--text-secondary);
            }

            .form-group .field-error { color: #c62828; font-weight: 500; }

            .form-row {
                display: grid;
                grid-template-columns: 1fr 1fr;
                gap: 16px;
            }

            /* Toggle switch */
            .toggle-row {
                display: flex;
                align-items: center;
                justify-content: space-between;
                padding: 12px 0;
            }

            .toggle-label-text { font-size: 15px; font-weight: 500; color: var(--text-primary); }
            .toggle-sub { font-size: 12px; color: var(--text-secondary); margin-top: 2px; }

            .toggle-switch {
                position: relative;
                width: 48px;
                height: 28px;
                flex-shrink: 0;
            }

            .toggle-switch input { opacity: 0; width: 0; height: 0; }

            .toggle-slider {
                position: absolute;
                cursor: pointer;
                inset: 0;
                background: #ccc;
                border-radius: 28px;
                transition: 0.3s;
            }

            .toggle-slider:before {
                content: "";
                position: absolute;
                width: 20px;
                height: 20px;
                left: 4px;
                bottom: 4px;
                background: white;
                border-radius: 50%;
                transition: 0.3s;
                box-shadow: 0 1px 3px rgba(0,0,0,0.3);
            }

            .toggle-switch input:checked + .toggle-slider { background: #4caf50; }
            .toggle-switch input:checked + .toggle-slider:before { transform: translateX(20px); }

            /* Range slider */
            .delay-slider {
                width: 100%;
                -webkit-appearance: none;
                height: 4px;
                border-radius: 2px;
                background: var(--divider);
                outline: none;
                margin: 12px 0 4px;
            }

            .delay-slider::-webkit-slider-thumb {
                -webkit-appearance: none;
                width: 20px;
                height: 20px;
                border-radius: 50%;
                background: var(--primary-color);
                cursor: pointer;
                box-shadow: 0 1px 4px rgba(0,0,0,0.3);
            }

            .delay-slider::-moz-range-thumb {
                width: 20px;
                height: 20px;
                border-radius: 50%;
                background: var(--primary-color);
                cursor: pointer;
                border: none;
                box-shadow: 0 1px 4px rgba(0,0,0,0.3);
            }

            .delay-presets {
                display: flex;
                gap: 6px;
                flex-wrap: wrap;
                margin-top: 12px;
            }

            .preset-btn {
                padding: 4px 12px;
                border: 1px solid var(--divider);
                border-radius: 16px;
                background: var(--bg);
                color: var(--text-secondary);
                font-size: 13px;
                cursor: pointer;
                transition: all 0.15s;
            }

            .preset-btn:hover,
            .preset-btn.active {
                border-color: var(--primary-color);
                color: var(--primary-color);
                background: rgba(3, 169, 244, 0.06);
            }

            .delay-display {
                font-size: 22px;
                font-weight: 600;
                color: var(--primary-color);
                text-align: center;
                margin: 8px 0 0;
            }

            /* Logbook */
            .logbook-card {
                background: var(--card-bg);
                border-radius: 16px;
                padding: 20px;
                margin-top: 24px;
                box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
            }

            .logbook-header {
                display: flex;
                align-items: center;
                justify-content: space-between;
                margin-bottom: 16px;
            }

            .logbook-header h3 {
                margin: 0;
                font-size: 16px;
                font-weight: 500;
                color: var(--text-primary);
            }

            .logbook-list {
                display: grid;
                gap: 2px;
                max-height: 400px;
                overflow-y: auto;
                scrollbar-width: thin;
            }

            .logbook-list::-webkit-scrollbar { width: 6px; }
            .logbook-list::-webkit-scrollbar-track { background: transparent; }
            .logbook-list::-webkit-scrollbar-thumb {
                background: var(--divider);
                border-radius: 3px;
            }
            .logbook-list::-webkit-scrollbar-thumb:hover { background: var(--text-secondary); }

            .logbook-entry {
                display: flex;
                align-items: center;
                gap: 12px;
                padding: 10px 0;
                border-bottom: 1px solid var(--divider);
            }

            .logbook-entry:last-child { border-bottom: none; }

            .logbook-dot {
                width: 10px;
                height: 10px;
                border-radius: 50%;
                flex-shrink: 0;
            }

            .logbook-dot.lock { background: #4caf50; }
            .logbook-dot.unlock { background: #ff9800; }
            .logbook-dot.auto { background: #9e9e9e; }
            .logbook-dot.failed { background: #f44336; }
            .logbook-dot.door { background: #2196f3; }

            .door-sensor-badge {
                display: flex;
                align-items: center;
                gap: 5px;
                padding: 4px 10px;
                border-radius: 16px;
                font-size: 13px;
                font-weight: 500;
                cursor: default;
                background: rgba(255,255,255,0.15);
                transition: background 0.2s;
            }
            .door-sensor-badge svg { width: 16px; height: 16px; flex-shrink: 0; }
            .door-sensor-badge.open { background: rgba(244,67,54,0.25); }
            .door-sensor-badge.closed { background: rgba(76,175,80,0.2); }

            .battery-badge {
                display: flex;
                align-items: center;
                gap: 5px;
                padding: 4px 10px;
                border-radius: 16px;
                font-size: 13px;
                font-weight: 500;
                cursor: default;
                background: rgba(255,255,255,0.15);
            }
            .battery-badge svg { width: 16px; height: 16px; flex-shrink: 0; }
            .battery-badge.high  { background: rgba(76,175,80,0.2); }
            .battery-badge.med   { background: rgba(255,193,7,0.25); }
            .battery-badge.low   { background: rgba(244,67,54,0.3); }

            .ls-wake-hint {
                font-size: 12px;
                color: var(--secondary-text-color, #888);
                margin-bottom: 16px;
                padding: 8px 12px;
                border-radius: 8px;
                background: rgba(255,193,7,0.12);
                border: 1px solid rgba(255,193,7,0.3);
            }
            .ls-row {
                display: flex;
                align-items: flex-start;
                justify-content: space-between;
                padding: 12px 0;
                border-bottom: 1px solid var(--divider-color, rgba(0,0,0,0.1));
                gap: 16px;
            }
            .ls-row:last-child { border-bottom: none; }
            .ls-label { flex: 1; }
            .ls-label-text { font-size: 14px; font-weight: 500; }
            .ls-hint { display: block; font-size: 12px; color: var(--secondary-text-color, #888); margin-top: 2px; }
            .ls-control { display: flex; align-items: center; gap: 6px; flex-shrink: 0; }
            .ls-number {
                width: 70px;
                padding: 6px 10px;
                border: 1px solid var(--divider-color, #ccc);
                border-radius: 6px;
                background: var(--card-background-color, #fff);
                color: var(--primary-text-color, #333);
                font-size: 14px;
                text-align: center;
            }

            .logbook-info { flex: 1; min-width: 0; }

            .logbook-state {
                font-size: 14px;
                color: var(--text-primary);
                display: block;
                white-space: nowrap;
                overflow: hidden;
                text-overflow: ellipsis;
            }

            .logbook-time {
                font-size: 12px;
                color: var(--text-secondary);
                display: block;
                margin-top: 2px;
            }

            .logbook-empty {
                text-align: center;
                color: var(--text-secondary);
                font-size: 14px;
                padding: 20px 0;
            }

            /* Lock action buttons */
            .lock-actions {
                display: flex;
                gap: 8px;
                flex-shrink: 0;
            }

            .lock-action-btn {
                display: inline-flex;
                align-items: center;
                gap: 6px;
                padding: 8px 14px;
                border: none;
                border-radius: 20px;
                font-size: 13px;
                font-weight: 500;
                cursor: pointer;
                transition: all 0.2s;
            }

            .lock-action-btn svg {
                width: 18px;
                height: 18px;
                flex-shrink: 0;
            }

            .lock-action-btn:disabled {
                opacity: 0.35;
                cursor: default;
                transform: none !important;
            }

            .lock-btn {
                background: rgba(76, 175, 80, 0.12);
                color: #2e7d32;
            }

            .lock-btn:not(:disabled):hover {
                background: rgba(76, 175, 80, 0.22);
                transform: translateY(-1px);
            }

            .unlock-btn {
                background: rgba(255, 152, 0, 0.12);
                color: #e65100;
            }

            .unlock-btn:not(:disabled):hover {
                background: rgba(255, 152, 0, 0.22);
                transform: translateY(-1px);
            }

            /* Responsive */
            @media (max-width: 600px) {
                .header { flex-direction: column; align-items: flex-start; }
                .toolbar { flex-direction: column; }
                .search-container { width: 100%; }

                .person-card { flex-wrap: wrap; }

                .person-actions {
                    width: 100%;
                    justify-content: flex-end;
                    margin-top: 8px;
                    padding-top: 12px;
                    border-top: 1px solid var(--divider);
                }

                .form-row { grid-template-columns: 1fr; }
                .stats { grid-template-columns: repeat(2, 1fr); }
                .auto-lock-badge { display: none; }
            }
        `;
    }

    connectedCallback() {
        super.connectedCallback();
        this.loadTranslations();
        this.loadCodes();
        this.loadConfig();
        this.loadLogbook();
        this._logbookTimer = setInterval(() => this.loadLogbook(), 30000);
    }

    disconnectedCallback() {
        super.disconnectedCallback();
        if (this._logbookTimer) {
            clearInterval(this._logbookTimer);
            this._logbookTimer = null;
        }
    }

    async loadCodes() {
        try {
            this.loading = true;
            this.error = null;
            const result = await this.hass.callWS({ type: "nimlykoder/list" });
            this.codes = result.codes || [];
            this.loading = false;
        } catch (err) {
            this.error = err.message;
            this.loading = false;
        }
    }

    async loadConfig() {
        try {
            const result = await this.hass.callWS({ type: "nimlykoder/config" });
            this.config = result;
            this.autoLockEnabled = result.auto_lock_enabled || false;
            this.autoLockDelay = result.auto_lock_delay || 300;
            this.doorSensorEntity = result.door_sensor || null;
            this.batteryEntity = result.battery_entity || null;
        } catch (err) {
            console.error("Failed to load config:", err);
        }
    }

    async loadTranslations() {
        try {
            const result = await this.hass.callWS({ type: "nimlykoder/translations" });
            if (result && result.translations) {
                this.translations = this._mergeTranslations(this._defaultTranslations(), result.translations);
            }
        } catch (err) {
            console.error("Failed to load translations:", err);
        }
    }

    async loadLogbook() {
        try {
            this.logbookLoading = true;
            const result = await this.hass.callWS({ type: "nimlykoder/activity" });
            this.logbookEntries = result.entries || [];
            this.logbookLoading = false;
        } catch (err) {
            console.error("Failed to load logbook:", err);
            this.logbookLoading = false;
        }
    }

    _formatEntryText(entry) {
        const { action, source, name } = entry;
        const unknown = this.t("activity.unknown");
        const cap = s => s.charAt(0).toUpperCase() + s.slice(1);
        if (action === "door_open")  return this.t("activity.door_open");
        if (action === "door_close") return this.t("activity.door_close");
        if (action === "auto_lock" || source === "auto") return this.t("activity.auto_lock");
        if (action === "lock" && !name) return this.t("activity.auto_lock");
        if (action === "failed_unlock") return `${name || unknown} — ${this.t("activity.wrong_code_unlock")}`;
        if (action === "failed_lock")   return `${name || unknown} — ${this.t("activity.wrong_code_lock")}`;
        const verb = action === "unlock" ? this.t("activity.verb_unlock") : this.t("activity.verb_lock");
        if (source === "keypad")      return `${name || unknown} ${verb} ${this.t("activity.with_code")}`;
        if (source === "fingerprint") return `${name || unknown} ${verb} ${this.t("activity.with_fingerprint")}`;
        if (source === "rfid")        return `${name || unknown} ${verb} ${this.t("activity.with_rfid")}`;
        if (source === "zigbee")      return `${cap(verb)} ${this.t("activity.via_zigbee")}`;
        if (source === "manual")      return `${cap(verb)} ${this.t("activity.manually")}`;
        return name ? `${name} ${verb}` : cap(verb);
    }

    _mergeTranslations(defaults, loaded) {
        const result = { ...defaults };
        for (const key of Object.keys(loaded)) {
            if (typeof loaded[key] === "object" && loaded[key] !== null && !Array.isArray(loaded[key])) {
                result[key] = this._mergeTranslations(defaults[key] || {}, loaded[key]);
            } else {
                result[key] = loaded[key];
            }
        }
        return result;
    }

    t(path, replacements = {}) {
        const keys = path.split(".");
        let value = this.translations;
        for (const key of keys) {
            if (value && typeof value === "object" && key in value) {
                value = value[key];
            } else {
                return path;
            }
        }
        if (typeof value === "string") {
            for (const [k, v] of Object.entries(replacements)) {
                value = value.replace(`{${k}}`, v);
            }
        }
        return value;
    }

    get cleanupTimeFormatted() {
        const time = this.config?.cleanup_time || "03:00:00";
        const [hours, minutes] = time.split(":");
        const hour = parseInt(hours);
        const min = minutes || "00";
        if (hour === 0) return `12:${min} AM`;
        if (hour < 12) return `${hour}:${min} AM`;
        if (hour === 12) return `12:${min} PM`;
        return `${hour - 12}:${min} PM`;
    }

    get filteredCodes() {
        if (!this.searchQuery) return this.codes;
        const query = this.searchQuery.toLowerCase();
        return this.codes.filter(
            (code) =>
                code.name.toLowerCase().includes(query) ||
                code.slot.toString().includes(query) ||
                code.type.toLowerCase().includes(query)
        );
    }

    get stats() {
        const total = this.codes.length;
        const permanent = this.codes.filter((c) => c.type === "permanent").length;
        const guest = this.codes.filter((c) => c.type === "guest").length;
        const expired = this.codes.filter(
            (c) => c.expiry && new Date(c.expiry) < new Date()
        ).length;
        return { total, permanent, guest, expired };
    }

    _formatDelay(seconds) {
        if (seconds < 60) return `${seconds}${this.t("time.seconds_unit")}`;
        if (seconds < 3600) {
            const m = Math.round(seconds / 60);
            return `${m}${this.t("time.minutes_unit")}`;
        }
        const h = (seconds / 3600).toFixed(1).replace(".0", "");
        return `${h}${this.t("time.hours_unit")}`;
    }

    _formatRelativeTime(unixTs) {
        const now = Date.now() / 1000;
        const diff = now - unixTs;
        if (diff < 60) return this.t("time.just_now");
        if (diff < 3600) return this.t("time.minutes_ago", { n: Math.floor(diff / 60) });
        if (diff < 86400) return this.t("time.hours_ago", { n: Math.floor(diff / 3600) });
        const d = new Date(unixTs * 1000);
        return d.toLocaleDateString(undefined, {
            day: "numeric",
            month: "short",
            hour: "2-digit",
            minute: "2-digit",
        });
    }

    _logbookDotClass(entry) {
        if (!entry) return "auto";
        if (entry.action === "door_open" || entry.action === "door_close") return "door";
        if (entry.action === "auto_lock" || entry.source === "auto") return "auto";
        if (entry.action === "lock" && !entry.name) return "auto";
        if (entry.action === "failed_unlock" || entry.action === "failed_lock") return "failed";
        if (entry.action === "unlock") return "unlock";
        return "lock";
    }

    getInitials(name) {
        return name.split(" ").map((n) => n[0]).join("").toUpperCase().slice(0, 2);
    }

    isExpired(code) {
        return code.expiry && new Date(code.expiry) < new Date();
    }

    getAvatarClass(code) {
        if (this.isExpired(code)) return "avatar-expired";
        return code.type === "permanent" ? "avatar-permanent" : "avatar-guest";
    }

    getBadgeClass(code) {
        if (this.isExpired(code)) return "badge-expired";
        return code.type === "permanent" ? "badge-permanent" : "badge-guest";
    }

    getBadgeText(code) {
        if (this.isExpired(code)) return this.t("status.expired");
        return code.type === "permanent" ? this.t("type.permanent") : this.t("type.guest");
    }

    formatDate(dateStr) {
        if (!dateStr) return "—";
        const date = new Date(dateStr);
        return date.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
    }

    render() {
        return html`
            ${this._renderAppHeader()}
            <div class="container">
                ${this.error ? this._renderError() : ""}
                ${this.loading
                    ? this._renderLoading()
                    : html`
                          ${this._renderLockStatus()}
                          ${this._renderStats()}
                          ${this._renderToolbar()}
                          ${this._renderPersonList()}
                          ${this._renderLogbook()}
                      `}
                ${this.showAddDialog ? this._renderAddDialog() : ""}
                ${this.showEditDialog ? this._renderEditDialog() : ""}
                ${this.showRemoveDialog ? this._renderRemoveDialog() : ""}
                ${this.showPinConfirmDialog ? this._renderPinConfirmDialog() : ""}
                ${this.showAutoLockDialog ? this._renderAutoLockDialog() : ""}
                ${this.showLockSettingsDialog ? this._renderLockSettingsDialog() : ""}
            </div>
        `;
    }

    _renderDoorSensorBadge() {
        if (!this.doorSensorEntity) return html``;
        const state = this.hass?.states?.[this.doorSensorEntity];
        if (!state) return html``;
        const isOpen = state.state === "on";
        const label = isOpen ? this.t("door.open") : this.t("door.closed");
        const cls = isOpen ? "open" : "closed";
        const doorOpenSvg = html`<svg viewBox="0 0 24 24" fill="currentColor"><path d="M19,3H5C3.89,3 3,3.89 3,5V19A2,2 0 0,0 5,21H19A2,2 0 0,0 21,19V5C21,3.89 20.1,3 19,3M13,17H11V15H13V17M13,13H11V7H13V13Z"/></svg>`;
        const doorClosedSvg = html`<svg viewBox="0 0 24 24" fill="currentColor"><path d="M8,3C6.89,3 6,3.89 6,5V21H18V5C18,3.89 17.11,3 16,3H8M12,17A1,1 0 0,1 11,16A1,1 0 0,1 12,15A1,1 0 0,1 13,16A1,1 0 0,1 12,17Z"/></svg>`;
        return html`
            <div class="door-sensor-badge ${cls}" title="${state.attributes?.friendly_name || this.doorSensorEntity}">
                ${isOpen ? doorOpenSvg : doorClosedSvg}
                ${label}
            </div>
        `;
    }

    _renderBatteryBadge() {
        if (!this.batteryEntity) return html``;
        const state = this.hass?.states?.[this.batteryEntity];
        if (!state || state.state === "unavailable" || state.state === "unknown") return html``;
        const pct = parseInt(state.state, 10);
        if (isNaN(pct)) return html``;
        const cls = pct > 50 ? "high" : pct > 20 ? "med" : "low";
        // Battery icon path changes at 10 % intervals for quick visual read
        const iconPath = pct > 90
            ? "M16,20H8V6H16M16.67,4H15V2H9V4H7.33A1.33,1.33 0 0,0 6,5.33V20.67C6,21.4 6.6,22 7.33,22H16.67A1.33,1.33 0 0,0 18,20.67V5.33C18,4.6 17.4,4 16.67,4Z"
            : pct > 60
            ? "M16,20H8V10H16M16.67,4H15V2H9V4H7.33A1.33,1.33 0 0,0 6,5.33V20.67C6,21.4 6.6,22 7.33,22H16.67A1.33,1.33 0 0,0 18,20.67V5.33C18,4.6 17.4,4 16.67,4Z"
            : pct > 30
            ? "M16,20H8V14H16M16.67,4H15V2H9V4H7.33A1.33,1.33 0 0,0 6,5.33V20.67C6,21.4 6.6,22 7.33,22H16.67A1.33,1.33 0 0,0 18,20.67V5.33C18,4.6 17.4,4 16.67,4Z"
            : "M16,20H8V17H16M16.67,4H15V2H9V4H7.33A1.33,1.33 0 0,0 6,5.33V20.67C6,21.4 6.6,22 7.33,22H16.67A1.33,1.33 0 0,0 18,20.67V5.33C18,4.6 17.4,4 16.67,4Z";
        return html`
            <div class="battery-badge ${cls}" title="${state.attributes?.friendly_name || this.batteryEntity}">
                <svg viewBox="0 0 24 24" fill="currentColor"><path d="${iconPath}"/></svg>
                ${pct}%
            </div>
        `;
    }

    _renderAppHeader() {
        const alLabel = this.autoLockEnabled
            ? this.t("auto_lock.badge_on", { delay: this._formatDelay(this.autoLockDelay) })
            : this.t("auto_lock.badge_off");
        return html`
            <div class="app-header">
                <button class="menu-btn" @click=${this._toggleMenu} aria-label="Open menu">
                    <svg viewBox="0 0 24 24" fill="currentColor">
                        <path d="M3,6H21V8H3V6M3,11H21V13H3V11M3,16H21V18H3V16Z"/>
                    </svg>
                </button>
                <div class="app-header-title">${this.t("title")}</div>
                <div class="header-actions">
                    ${this._renderBatteryBadge()}
                    ${this._renderDoorSensorBadge()}
                    <div
                        class="auto-lock-badge ${this.autoLockEnabled ? "active" : ""}"
                        @click=${() => { this.showAutoLockDialog = true; }}
                        title="${this.t("auto_lock.settings")}"
                    >
                        <svg viewBox="0 0 24 24" fill="currentColor">
                            <path d="M12,17A2,2 0 0,0 14,15C14,13.89 13.1,13 12,13A2,2 0 0,0 10,15A2,2 0 0,0 12,17M18,8A2,2 0 0,1 20,10V20A2,2 0 0,1 18,22H6A2,2 0 0,1 4,20V10C4,8.89 4.9,8 6,8H7V6A5,5 0 0,1 12,1A5,5 0 0,1 17,6V8H18M12,3A3,3 0 0,0 9,6V8H15V6A3,3 0 0,0 12,3Z"/>
                        </svg>
                        ${alLabel}
                    </div>
                    <button class="menu-btn" @click=${() => { this.showLockSettingsDialog = true; this.lockSettings = null; this.lockSettingsError = null; }} title="${this.t("lock_settings.dialog_title")}">
                        <svg viewBox="0 0 24 24" fill="currentColor">
                            <path d="M3,17V19H9V17H3M3,5V7H13V5H3M13,21V19H21V17H13V15H11V21H13M7,9V11H3V13H7V15H9V9H7M21,13V11H11V13H21M15,9H17V7H21V5H17V3H15V9Z"/>
                        </svg>
                    </button>
                    <button class="menu-btn" @click=${() => { this.showAutoLockDialog = true; }} aria-label="Settings">
                        <svg viewBox="0 0 24 24" fill="currentColor">
                            <path d="M12,15.5A3.5,3.5 0 0,1 8.5,12A3.5,3.5 0 0,1 12,8.5A3.5,3.5 0 0,1 15.5,12A3.5,3.5 0 0,1 12,15.5M19.43,12.97C19.47,12.65 19.5,12.33 19.5,12C19.5,11.67 19.47,11.34 19.43,11L21.54,9.37C21.73,9.22 21.78,8.95 21.66,8.73L19.66,5.27C19.54,5.05 19.27,4.96 19.05,5.05L16.56,6.05C16.04,5.66 15.5,5.32 14.87,5.07L14.5,2.42C14.46,2.18 14.25,2 14,2H10C9.75,2 9.54,2.18 9.5,2.42L9.13,5.07C8.5,5.32 7.96,5.66 7.44,6.05L4.95,5.05C4.73,4.96 4.46,5.05 4.34,5.27L2.34,8.73C2.21,8.95 2.27,9.22 2.46,9.37L4.57,11C4.53,11.34 4.5,11.67 4.5,12C4.5,12.33 4.53,12.65 4.57,12.97L2.46,14.63C2.27,14.78 2.21,15.05 2.34,15.27L4.34,18.73C4.46,18.95 4.73,19.03 4.95,18.95L7.44,17.94C7.96,18.34 8.5,18.68 9.13,18.93L9.5,21.58C9.54,21.82 9.75,22 10,22H14C14.25,22 14.46,21.82 14.5,21.58L14.87,18.93C15.5,18.68 16.04,18.34 16.56,17.94L19.05,18.95C19.27,19.03 19.54,18.95 19.66,18.73L21.66,15.27C21.78,15.05 21.73,14.78 21.54,14.63L19.43,12.97Z"/>
                        </svg>
                    </button>
                </div>
            </div>
        `;
    }

    _toggleMenu() {
        this.dispatchEvent(new CustomEvent("hass-toggle-menu", { bubbles: true, composed: true }));
    }

    _renderLockStatus() {
        const lockEntityId = this.config?.lock_entity || "";
        const lockState = lockEntityId ? this.hass?.states?.[lockEntityId] : null;
        const lockName = lockState?.attributes?.friendly_name || "Nimly";
        const state = lockState?.state || "unknown";
        const isLocked = state === "locked";
        const isUnlocked = state === "unlocked";
        const stateClass = isLocked ? "locked" : isUnlocked ? "unlocked" : "unknown";
        const stateText = isLocked ? this.t("lock.locked") : isUnlocked ? this.t("lock.unlocked") : this.t("lock.unknown_state");
        const availableSlots = (this.config?.slot_max || 99) - (this.config?.slot_min || 0) + 1 - this.codes.length;

        return html`
            <div class="lock-status-bar">
                <div class="lock-status-icon ${stateClass}">
                    ${isLocked ? html`
                        <svg viewBox="0 0 24 24" fill="currentColor">
                            <path d="M12,17A2,2 0 0,0 14,15C14,13.89 13.1,13 12,13A2,2 0 0,0 10,15A2,2 0 0,0 12,17M18,8A2,2 0 0,1 20,10V20A2,2 0 0,1 18,22H6A2,2 0 0,1 4,20V10C4,8.89 4.9,8 6,8H7V6A5,5 0 0,1 12,1A5,5 0 0,1 17,6V8H18M12,3A3,3 0 0,0 9,6V8H15V6A3,3 0 0,0 12,3Z"/>
                        </svg>
                    ` : html`
                        <svg viewBox="0 0 24 24" fill="currentColor">
                            <path d="M18,8A2,2 0 0,1 20,10V20A2,2 0 0,1 18,22H6C4.89,22 4,21.1 4,20V10A2,2 0 0,1 6,8H15V6A3,3 0 0,0 12,3A3,3 0 0,0 9,6H7A5,5 0 0,1 12,1A5,5 0 0,1 17,6V8H18M12,17A2,2 0 0,0 14,15A2,2 0 0,0 12,13A2,2 0 0,0 10,15A2,2 0 0,0 12,17Z"/>
                        </svg>
                    `}
                </div>
                <div class="lock-status-info">
                    <div class="lock-status-name">${lockName}</div>
                    <div class="lock-status-state">
                        <span class="dot ${stateClass}"></span>
                        ${stateText}
                    </div>
                </div>
                <div class="lock-actions">
                    <button
                        class="lock-action-btn lock-btn"
                        ?disabled=${isLocked || !lockEntityId}
                        @click=${this._lockDoor}
                        title="${this.t("lock.lock")}"
                    >
                        <svg viewBox="0 0 24 24" fill="currentColor">
                            <path d="M12,17A2,2 0 0,0 14,15C14,13.89 13.1,13 12,13A2,2 0 0,0 10,15A2,2 0 0,0 12,17M18,8A2,2 0 0,1 20,10V20A2,2 0 0,1 18,22H6A2,2 0 0,1 4,20V10C4,8.89 4.9,8 6,8H7V6A5,5 0 0,1 12,1A5,5 0 0,1 17,6V8H18M12,3A3,3 0 0,0 9,6V8H15V6A3,3 0 0,0 12,3Z"/>
                        </svg>
                        ${this.t("lock.lock")}
                    </button>
                    <button
                        class="lock-action-btn unlock-btn"
                        ?disabled=${isUnlocked || !lockEntityId}
                        @click=${this._unlockDoor}
                        title="${this.t("lock.unlock")}"
                    >
                        <svg viewBox="0 0 24 24" fill="currentColor">
                            <path d="M18,8A2,2 0 0,1 20,10V20A2,2 0 0,1 18,22H6C4.89,22 4,21.1 4,20V10A2,2 0 0,1 6,8H15V6A3,3 0 0,0 12,3A3,3 0 0,0 9,6H7A5,5 0 0,1 12,1A5,5 0 0,1 17,6V8H18M12,17A2,2 0 0,0 14,15A2,2 0 0,0 12,13A2,2 0 0,0 10,15A2,2 0 0,0 12,17Z"/>
                        </svg>
                        ${this.t("lock.unlock")}
                    </button>
                </div>
            </div>
        `;
    }

    _renderStats() {
        const { total, permanent, guest, expired } = this.stats;
        const autoExpireEnabled = this.config?.auto_expire !== false;

        return html`
            <div class="stats">
                <div class="stat-card">
                    <div class="stat-value">${total}</div>
                    <div class="stat-label">${this.t("stats.total")}</div>
                </div>
                <div class="stat-card permanent">
                    <div class="stat-value">${permanent}</div>
                    <div class="stat-label">${this.t("stats.permanent")}</div>
                </div>
                <div class="stat-card guest">
                    <div class="stat-value">${guest}</div>
                    <div class="stat-label">${this.t("stats.guest")}</div>
                </div>
                <div class="stat-card expired">
                    <div class="stat-header">
                        <div class="stat-value">${expired}</div>
                        <svg
                            class="info-icon"
                            viewBox="0 0 24 24"
                            fill="currentColor"
                            @click=${(e) => { e.stopPropagation(); this.showExpiredInfo = !this.showExpiredInfo; }}
                            @mouseenter=${() => this.showExpiredInfo = true}
                            @mouseleave=${() => this.showExpiredInfo = false}
                        >
                            <path d="M13,9H11V7H13M13,17H11V11H13M12,2A10,10 0 0,0 2,12A10,10 0 0,0 12,22A10,10 0 0,0 22,12A10,10 0 0,0 12,2Z"/>
                        </svg>
                    </div>
                    <div class="stat-label">${this.t("stats.expired")}</div>
                    ${this.showExpiredInfo ? html`
                        <div class="info-tooltip">
                            <h4>
                                <svg viewBox="0 0 24 24" fill="currentColor">
                                    <path d="M12,20A8,8 0 0,0 20,12A8,8 0 0,0 12,4A8,8 0 0,0 4,12A8,8 0 0,0 12,20M12,2A10,10 0 0,1 22,12A10,10 0 0,1 12,22C6.47,22 2,17.5 2,12A10,10 0 0,1 12,2M12.5,7V12.25L17,14.92L16.25,16.15L11,13V7H12.5Z"/>
                                </svg>
                                ${this.t("expired_info.title")}
                            </h4>
                            <p>
                                ${this.t("expired_info.description")}
                                ${autoExpireEnabled
                                    ? html`<br><br>${this.t("expired_info.auto_cleanup", { time: this.cleanupTimeFormatted })}`
                                    : html`<br><br>${this.t("expired_info.manual_cleanup")}`
                                }
                            </p>
                        </div>
                    ` : ""}
                </div>
            </div>
        `;
    }

    _renderToolbar() {
        return html`
            <div class="toolbar">
                <div class="search-container">
                    <svg class="search-icon" width="20" height="20" viewBox="0 0 24 24" fill="currentColor">
                        <path d="M9.5,3A6.5,6.5 0 0,1 16,9.5C16,11.11 15.41,12.59 14.44,13.73L14.71,14H15.5L20.5,19L19,20.5L14,15.5V14.71L13.73,14.44C12.59,15.41 11.11,16 9.5,16A6.5,6.5 0 0,1 3,9.5A6.5,6.5 0 0,1 9.5,3M9.5,5C7,5 5,7 5,9.5C5,12 7,14 9.5,14C12,14 14,12 14,9.5C14,7 12,5 9.5,5Z"/>
                    </svg>
                    <input
                        type="text"
                        class="search-input"
                        placeholder="${this.t("search_placeholder")}"
                        .value=${this.searchQuery}
                        @input=${(e) => (this.searchQuery = e.target.value)}
                    />
                </div>
                <button class="btn btn-primary" @click=${() => this._openAddDialog()}>
                    <svg viewBox="0 0 24 24" fill="currentColor">
                        <path d="M19,13H13V19H11V13H5V11H11V5H13V11H19V13Z"/>
                    </svg>
                    ${this.t("add_code")}
                </button>
            </div>
        `;
    }

    _renderPersonList() {
        const codes = this.filteredCodes;

        if (this.codes.length === 0) return this._renderEmptyState();

        if (codes.length === 0) {
            return html`
                <div class="empty-state">
                    <h2>${this.t("no_results.title")}</h2>
                    <p>${this.t("no_results.description")}</p>
                </div>
            `;
        }

        return html`
            <div class="person-list">
                ${codes.map((code) => this._renderPersonCard(code))}
            </div>
        `;
    }

    _renderPersonCard(code) {
        return html`
            <div class="person-card">
                <div class="person-avatar ${this.getAvatarClass(code)}">
                    ${this.getInitials(code.name)}
                </div>
                <div class="person-info">
                    <h3 class="person-name">${code.name}</h3>
                    <div class="person-details">
                        <span class="person-detail">
                            <svg viewBox="0 0 24 24" fill="currentColor">
                                <path d="M12,1L3,5V11C3,16.55 6.84,21.74 12,23C17.16,21.74 21,16.55 21,11V5L12,1M12,5A3,3 0 0,1 15,8A3,3 0 0,1 12,11A3,3 0 0,1 9,8A3,3 0 0,1 12,5M17.13,17C15.92,18.85 14.11,20.24 12,20.92C9.89,20.24 8.08,18.85 6.87,17C6.53,16.5 6.24,16 6,15.47C6,13.82 8.71,12.47 12,12.47C15.29,12.47 18,13.79 18,15.47C17.76,16 17.47,16.5 17.13,17Z"/>
                            </svg>
                            ${this.t("slot_label")} ${code.slot}
                        </span>
                        ${code.expiry ? html`
                            <span class="person-detail">
                                <svg viewBox="0 0 24 24" fill="currentColor">
                                    <path d="M12,20A8,8 0 0,0 20,12A8,8 0 0,0 12,4A8,8 0 0,0 4,12A8,8 0 0,0 12,20M12,2A10,10 0 0,1 22,12A10,10 0 0,1 12,22C6.47,22 2,17.5 2,12A10,10 0 0,1 12,2M12.5,7V12.25L17,14.92L16.25,16.15L11,13V7H12.5Z"/>
                                </svg>
                                ${this.isExpired(code) ? this.t("expired_on") : this.t("expires")} ${this.formatDate(code.expiry)}
                            </span>
                        ` : ""}
                    </div>
                </div>
                <span class="badge ${this.getBadgeClass(code)}">${this.getBadgeText(code)}</span>
                <div class="person-actions">
                    <button
                        class="btn btn-icon btn-secondary"
                        @click=${() => { this.editingCode = code; this.showEditDialog = true; }}
                        title="${this.t("dialog.edit_title")}"
                    >
                        <svg viewBox="0 0 24 24" fill="currentColor">
                            <path d="M20.71,7.04C21.1,6.65 21.1,6 20.71,5.63L18.37,3.29C18,2.9 17.35,2.9 16.96,3.29L15.12,5.12L18.87,8.87M3,17.25V21H6.75L17.81,9.93L14.06,6.18L3,17.25Z"/>
                        </svg>
                    </button>
                    <button
                        class="btn btn-icon btn-secondary"
                        @click=${() => { this.removingCode = code; this.showRemoveDialog = true; }}
                        title="${this.t("dialog.remove")}"
                    >
                        <svg viewBox="0 0 24 24" fill="currentColor">
                            <path d="M19,4H15.5L14.5,3H9.5L8.5,4H5V6H19M6,19A2,2 0 0,0 8,21H16A2,2 0 0,0 18,19V7H6V19Z"/>
                        </svg>
                    </button>
                </div>
            </div>
        `;
    }

    _renderLogbook() {
        return html`
            <div class="logbook-card">
                <div class="logbook-header">
                    <h3>${this.t("logbook.title")}</h3>
                    <button class="btn btn-text" @click=${() => this.loadLogbook()} style="padding:4px 12px;font-size:13px;">
                        ${this.t("logbook.refresh")}
                    </button>
                </div>
                ${this.logbookLoading ? html`<div class="spinner spinner-sm"></div>` : ""}
                ${!this.logbookLoading && this.logbookEntries.length === 0 ? html`
                    <p class="logbook-empty">${this.t("logbook.empty")}</p>
                ` : ""}
                <div class="logbook-list">
                    ${this.logbookEntries.map(entry => html`
                        <div class="logbook-entry">
                            <span class="logbook-dot ${this._logbookDotClass(entry)}"></span>
                            <div class="logbook-info">
                                <span class="logbook-state">${this._formatEntryText(entry)}</span>
                                <span class="logbook-time">${this._formatRelativeTime(new Date(entry.ts).getTime() / 1000)}</span>
                            </div>
                        </div>
                    `)}
                </div>
            </div>
        `;
    }

    _renderLockSettingsDialog() {
        const ls = this.lockSettings;
        const closeSvg = html`<svg viewBox="0 0 24 24" fill="currentColor"><path d="M19,6.41L17.59,5L12,10.59L6.41,5L5,6.41L10.59,12L5,17.59L6.41,19L12,13.41L17.59,19L19,17.59L13.41,12L19,6.41Z"/></svg>`;
        const close = () => { this.showLockSettingsDialog = false; };

        const _toggle = (name) => html`
            <div class="ls-row">
                <div class="ls-label">
                    <div class="ls-label-text">${this.t(`lock_settings.${name}`)}</div>
                    <span class="ls-hint">${this.t(`lock_settings.${name}_hint`)}</span>
                </div>
                <div class="ls-control">
                    <label class="toggle-switch">
                        <input type="checkbox"
                            .checked=${!!ls[name]}
                            @change=${(e) => { this.lockSettings = {...ls, [name]: e.target.checked}; }}
                        />
                        <span class="toggle-slider"></span>
                    </label>
                </div>
            </div>
        `;

        const _number = (name, min, max) => html`
            <div class="ls-row">
                <div class="ls-label">
                    <div class="ls-label-text">${this.t(`lock_settings.${name}`)}</div>
                    <span class="ls-hint">${this.t(`lock_settings.${name}_hint`)}</span>
                </div>
                <div class="ls-control">
                    <input type="number" class="ls-number"
                        min="${min}" max="${max}"
                        .value=${String(ls[name] ?? "")}
                        @change=${(e) => {
                            const v = Math.max(min, Math.min(max, parseInt(e.target.value) || min));
                            this.lockSettings = {...ls, [name]: v};
                        }}
                    />
                </div>
            </div>
        `;

        return html`
            <div class="dialog-overlay" @click=${close}>
                <div class="dialog" @click=${(e) => e.stopPropagation()}>
                    <div class="dialog-header">
                        <h2>${this.t("lock_settings.dialog_title")}</h2>
                        <button class="btn btn-icon btn-text" @click=${close}>${closeSvg}</button>
                    </div>
                    <div class="dialog-content">
                        ${this.lockSettingsError ? html`<div class="error-msg" style="margin-bottom:12px;">${this.lockSettingsError}</div>` : ""}
                        <div class="ls-wake-hint">${this.t("lock_settings.wake_hint")}</div>
                        <button class="btn btn-secondary" style="margin-bottom:16px;"
                            @click=${this._loadLockSettings}
                            ?disabled=${this.lockSettingsLoading}>
                            ${this.lockSettingsLoading ? this.t("lock_settings.loading") : this.t("lock_settings.load")}
                        </button>

                        ${ls ? html`
                            <!-- Sound volume -->
                            <div class="ls-row">
                                <div class="ls-label">
                                    <div class="ls-label-text">${this.t("lock_settings.sound_volume")}</div>
                                    <span class="ls-hint">${this.t("lock_settings.sound_volume_hint")}</span>
                                </div>
                                <div class="ls-control">
                                    ${[0, 1, 2].map(v => html`
                                        <button class="preset-btn ${ls.sound_volume === v ? "active" : ""}"
                                            @click=${() => { this.lockSettings = {...ls, sound_volume: v}; }}>
                                            ${this.t(`lock_settings.sound_${v}`)}
                                        </button>
                                    `)}
                                </div>
                            </div>
                            ${_toggle("enable_one_touch_locking")}
                            ${_toggle("enable_privacy_mode_button")}
                            ${_number("wrong_code_attempt_limit", 1, 10)}
                            ${_number("user_code_temporary_disable_time", 0, 254)}
                        ` : ""}
                    </div>
                    <div class="dialog-actions">
                        <button class="btn btn-secondary" @click=${close}>${this.t("dialog.cancel")}</button>
                        ${ls ? html`
                            <button class="btn btn-primary"
                                @click=${this._saveAllLockSettings}
                                ?disabled=${this.lockSettingsSaving}>
                                ${this.lockSettingsSaving ? this.t("lock_settings.saving") : this.t("lock_settings.save_all")}
                            </button>
                        ` : ""}
                    </div>
                </div>
            </div>
        `;
    }

    async _loadLockSettings() {
        this.lockSettingsLoading = true;
        this.lockSettingsError = null;
        this.requestUpdate();
        try {
            const result = await this.hass.callWS({ type: "nimlykoder/get_lock_settings" });
            this.lockSettings = { ...result.settings };
        } catch (err) {
            this.lockSettingsError = this.t("lock_settings.read_error", { error: err.message });
        } finally {
            this.lockSettingsLoading = false;
            this.requestUpdate();
        }
    }

    async _saveAllLockSettings() {
        const ls = this.lockSettings;
        if (!ls) return;
        this.lockSettingsSaving = true;
        this.lockSettingsError = null;
        this.requestUpdate();
        const errors = [];
        for (const [name, value] of Object.entries(ls)) {
            if (value === undefined || value === null) continue;
            try {
                await this.hass.callWS({ type: "nimlykoder/set_lock_setting", setting: name, value });
            } catch (err) {
                errors.push(`${name}: ${err.message}`);
            }
        }
        this.lockSettingsSaving = false;
        if (errors.length === 0) {
            this.showLockSettingsDialog = false;
        } else {
            this.lockSettingsError = errors.join("; ");
        }
        this.requestUpdate();
    }

    _renderAutoLockDialog() {
        const presets = [
            { label: `30${this.t("time.seconds_unit")}`, value: 30 },
            { label: `1${this.t("time.minutes_unit")}`, value: 60 },
            { label: `5${this.t("time.minutes_unit")}`, value: 300 },
            { label: `10${this.t("time.minutes_unit")}`, value: 600 },
            { label: `30${this.t("time.minutes_unit")}`, value: 1800 },
        ];

        return html`
            <div class="dialog-overlay" @click=${() => { this.showAutoLockDialog = false; }}>
                <div class="dialog" @click=${(e) => e.stopPropagation()}>
                    <div class="dialog-header">
                        <h2>${this.t("auto_lock.dialog_title")}</h2>
                        <button class="btn btn-icon btn-text" @click=${() => { this.showAutoLockDialog = false; }}>
                            <svg viewBox="0 0 24 24" fill="currentColor">
                                <path d="M19,6.41L17.59,5L12,10.59L6.41,5L5,6.41L10.59,12L5,17.59L6.41,19L12,13.41L17.59,19L19,17.59L13.41,12L19,6.41Z"/>
                            </svg>
                        </button>
                    </div>
                    <div class="dialog-content">
                        <div class="toggle-row">
                            <div>
                                <div class="toggle-label-text">${this.t("auto_lock.enable")}</div>
                                <div class="toggle-sub">${this.t("auto_lock.enable_sub")}</div>
                            </div>
                            <label class="toggle-switch">
                                <input
                                    type="checkbox"
                                    .checked=${this.autoLockEnabled}
                                    @change=${(e) => { this.autoLockEnabled = e.target.checked; }}
                                />
                                <span class="toggle-slider"></span>
                            </label>
                        </div>

                        ${this.autoLockEnabled ? html`
                            <div class="form-group" style="margin-top:20px;">
                                <label>${this.t("auto_lock.delay")}</label>
                                <div class="delay-display">${this._formatDelay(this.autoLockDelay)}</div>
                                <input
                                    type="range"
                                    class="delay-slider"
                                    min="10"
                                    max="3600"
                                    step="10"
                                    .value=${String(this.autoLockDelay)}
                                    @input=${(e) => { this.autoLockDelay = parseInt(e.target.value); }}
                                />
                                <div class="delay-presets">
                                    ${presets.map(p => html`
                                        <button
                                            class="preset-btn ${this.autoLockDelay === p.value ? "active" : ""}"
                                            @click=${() => { this.autoLockDelay = p.value; }}
                                        >${p.label}</button>
                                    `)}
                                </div>
                            </div>
                        ` : ""}
                    </div>
                    <div class="dialog-actions">
                        <button class="btn btn-secondary" @click=${() => { this.showAutoLockDialog = false; }}>${this.t("dialog.cancel")}</button>
                        <button class="btn btn-primary" @click=${this._saveAutoLock}>${this.t("dialog.save")}</button>
                    </div>
                </div>
            </div>
        `;
    }

    async _lockDoor() {
        const entityId = this.config?.lock_entity;
        if (!entityId) return;
        try {
            await this.hass.callService("lock", "lock", { entity_id: entityId });
        } catch (err) {
            this.error = this.t("errors.lock_failed", {error: err.message});
        }
    }

    async _unlockDoor() {
        const entityId = this.config?.lock_entity;
        if (!entityId) return;
        try {
            await this.hass.callService("lock", "unlock", { entity_id: entityId });
        } catch (err) {
            this.error = this.t("errors.unlock_failed", {error: err.message});
        }
    }

    async _saveAutoLock() {
        this._autoLockSaving = true;
        this.requestUpdate();
        try {
            await this.hass.callWS({
                type: "nimlykoder/set_auto_lock",
                enabled: this.autoLockEnabled,
                delay: this.autoLockDelay,
            });
            this.showAutoLockDialog = false;
        } catch (err) {
            this.error = this.t("errors.auto_lock_save_failed", {error: err.message});
            this.showAutoLockDialog = false;
        } finally {
            this._autoLockSaving = false;
        }
    }

    _renderEmptyState() {
        return html`
            <div class="empty-state">
                <div class="empty-icon">
                    <svg viewBox="0 0 24 24" fill="currentColor">
                        <path d="M12,4A4,4 0 0,1 16,8A4,4 0 0,1 12,12A4,4 0 0,1 8,8A4,4 0 0,1 12,4M12,14C16.42,14 20,15.79 20,18V20H4V18C4,15.79 7.58,14 12,14Z"/>
                    </svg>
                </div>
                <h2>${this.t("empty.title")}</h2>
                <p>${this.t("empty.description")}</p>
                <button class="btn btn-primary" @click=${() => this._openAddDialog()}>
                    <svg viewBox="0 0 24 24" fill="currentColor">
                        <path d="M19,13H13V19H11V13H5V11H11V5H13V11H19V13Z"/>
                    </svg>
                    ${this.t("empty.add_first")}
                </button>
            </div>
        `;
    }

    _renderLoading() {
        return html`
            <div class="loading-container">
                <div class="spinner"></div>
                <p>${this.t("loading")}</p>
            </div>
        `;
    }

    _renderError() {
        return html`
            <div class="error-banner">
                <svg viewBox="0 0 24 24" fill="currentColor">
                    <path d="M13,13H11V7H13M13,17H11V15H13M12,2A10,10 0 0,0 2,12A10,10 0 0,0 12,22A10,10 0 0,0 22,12A10,10 0 0,0 12,2Z"/>
                </svg>
                <span>${this.error}</span>
                <button class="btn btn-text" @click=${() => { this.error = null; this.loadCodes(); }}>${this.t("retry")}</button>
            </div>
        `;
    }

    _renderAddDialog() {
        return html`
            <div class="dialog-overlay" @click=${this._closeAddDialog}>
                <div class="dialog" @click=${(e) => e.stopPropagation()}>
                    <div class="dialog-header">
                        <h2>${this.t("dialog.add_title")}</h2>
                        <button class="btn btn-icon btn-text" @click=${this._closeAddDialog}>
                            <svg viewBox="0 0 24 24" fill="currentColor">
                                <path d="M19,6.41L17.59,5L12,10.59L6.41,5L5,6.41L10.59,12L5,17.59L6.41,19L12,13.41L17.59,19L19,17.59L13.41,12L19,6.41Z"/>
                            </svg>
                        </button>
                    </div>
                    <div class="dialog-content" @click=${(e) => e.stopPropagation()}>
                        <div class="form-group">
                            <label for="add-name">${this.t("dialog.name")} *</label>
                            <input type="text" id="add-name" placeholder="${this.t("dialog.name_placeholder")}" required />
                        </div>
                        <div class="form-group">
                            <label for="add-pin">${this.t("dialog.pin_code")} *</label>
                            <input type="password" id="add-pin" placeholder="${this.t("dialog.pin_placeholder")}" pattern="[0-9]{4,6}" maxlength="6" required />
                            <small>${this.t("dialog.pin_hint")}</small>
                        </div>
                        <div class="form-row">
                            <div class="form-group">
                                <label for="add-type">${this.t("dialog.type")} *</label>
                                <select id="add-type" @change=${this._onTypeChange} @click=${(e) => e.stopPropagation()}>
                                    <option value="permanent">${this.t("type.permanent")}</option>
                                    <option value="guest">${this.t("type.guest")}</option>
                                </select>
                            </div>
                            <div class="form-group">
                                <label for="add-slot">${this.t("dialog.slot")}</label>
                                <input type="number" id="add-slot" min="1" max="99" .value=${this.suggestedSlot !== null ? String(this.suggestedSlot) : ""} />
                                <small>${this.t("dialog.next_available")}: ${this.suggestedSlot !== null ? this.suggestedSlot : "..."}</small>
                            </div>
                        </div>
                        <div class="form-group" id="expiry-group" style="display: none;">
                            <label for="add-expiry">${this.t("dialog.expiry")}</label>
                            <input type="date" id="add-expiry" />
                        </div>
                    </div>
                    <div class="dialog-actions">
                        <button class="btn btn-secondary" @click=${this._closeAddDialog}>${this.t("dialog.cancel")}</button>
                        <button class="btn btn-primary" @click=${this._handleAddSubmit}>${this.t("dialog.add")}</button>
                    </div>
                </div>
            </div>
        `;
    }

    _renderEditDialog() {
        if (!this.editingCode) return "";
        const isGuest = this.editingCode.type === "guest";
        return html`
            <div class="dialog-overlay" @click=${this._closeEditDialog}>
                <div class="dialog" @click=${(e) => e.stopPropagation()}>
                    <div class="dialog-header">
                        <h2>${this.t("dialog.edit_title")}</h2>
                        <button class="btn btn-icon btn-text" @click=${this._closeEditDialog}>
                            <svg viewBox="0 0 24 24" fill="currentColor">
                                <path d="M19,6.41L17.59,5L12,10.59L6.41,5L5,6.41L10.59,12L5,17.59L6.41,19L12,13.41L17.59,19L19,17.59L13.41,12L19,6.41Z"/>
                            </svg>
                        </button>
                    </div>
                    <div class="dialog-content">
                        <div class="form-group">
                            <label for="edit-name">${this.t("dialog.name")}</label>
                            <input type="text" id="edit-name" .value=${this.editingCode.name} placeholder="${this.t("dialog.name_placeholder")}" @input=${() => this.editFormError = null} />
                            ${this.editFormError === "name_required" ? html`<small class="field-error">${this.t("errors.name_required")}</small>` : ""}
                        </div>
                        ${isGuest ? html`
                            <div class="form-group">
                                <label for="edit-expiry">${this.t("dialog.expiry")}</label>
                                <input type="date" id="edit-expiry" .value=${this.editingCode.expiry || ""} />
                                <small>${this.t("dialog.expiry_hint")}</small>
                            </div>
                        ` : html`
                            <p style="color: var(--text-secondary); margin-bottom: 16px;">${this.t("dialog.permanent_no_expiry")}</p>
                        `}
                        <div class="form-group" style="border-top: 1px solid var(--divider); padding-top: 16px; margin-top: 16px;">
                            <label for="edit-pin">${this.t("dialog.change_pin")}</label>
                            <input type="text" id="edit-pin" placeholder="${this.t("dialog.pin_placeholder")}" pattern="[0-9]{4,6}" maxlength="6" inputmode="numeric" @input=${() => this.editFormError = null} />
                            <small style="color: var(--warning-color, #ff9800);">${this.t("dialog.pin_change_warning")}</small>
                            ${this.editFormError === "pin_invalid" ? html`<small class="field-error">${this.t("errors.pin_invalid")}</small>` : ""}
                        </div>
                    </div>
                    <div class="dialog-actions">
                        <button class="btn btn-secondary" @click=${this._closeEditDialog}>${this.t("dialog.cancel")}</button>
                        <button class="btn btn-primary" @click=${this._handleEditSubmit}>${this.t("dialog.save")}</button>
                    </div>
                </div>
            </div>
        `;
    }

    _renderPinConfirmDialog() {
        if (!this.showPinConfirmDialog || !this.pendingPinUpdate) return "";
        return html`
            <div class="dialog-overlay" @click=${this._closePinConfirmDialog}>
                <div class="dialog" @click=${(e) => e.stopPropagation()}>
                    <div class="dialog-header">
                        <h2>${this.t("dialog.confirm_pin_change")}</h2>
                        <button class="btn btn-icon btn-text" @click=${this._closePinConfirmDialog}>
                            <svg viewBox="0 0 24 24" fill="currentColor">
                                <path d="M19,6.41L17.59,5L12,10.59L6.41,5L5,6.41L10.59,12L5,17.59L6.41,19L12,13.41L17.59,19L19,17.59L13.41,12L19,6.41Z"/>
                            </svg>
                        </button>
                    </div>
                    <div class="dialog-content">
                        <div style="background: var(--warning-color, #ff9800); color: white; padding: 16px; border-radius: 8px; margin-bottom: 16px;">
                            <strong>⚠️ ${this.t("dialog.pin_warning_title")}</strong>
                            <p style="margin: 8px 0 0 0;">${this.t("dialog.pin_warning_message")}</p>
                        </div>
                        <p>${this.t("dialog.pin_confirm_question", { name: this.pendingPinUpdate.name })}</p>
                    </div>
                    <div class="dialog-actions">
                        <button class="btn btn-secondary" @click=${this._closePinConfirmDialog}>${this.t("dialog.cancel")}</button>
                        <button class="btn btn-primary" style="background: var(--warning-color, #ff9800);" @click=${this._confirmPinUpdate}>${this.t("dialog.confirm_change")}</button>
                    </div>
                </div>
            </div>
        `;
    }

    _renderRemoveDialog() {
        if (!this.removingCode) return "";
        return html`
            <div class="dialog-overlay" @click=${this._closeRemoveDialog}>
                <div class="dialog" @click=${(e) => e.stopPropagation()}>
                    <div class="dialog-header">
                        <h2>${this.t("dialog.remove_title")}</h2>
                        <button class="btn btn-icon btn-text" @click=${this._closeRemoveDialog}>
                            <svg viewBox="0 0 24 24" fill="currentColor">
                                <path d="M19,6.41L17.59,5L12,10.59L6.41,5L5,6.41L10.59,12L5,17.59L6.41,19L12,13.41L17.59,19L19,17.59L13.41,12L19,6.41Z"/>
                            </svg>
                        </button>
                    </div>
                    <div class="dialog-content">
                        <p>${this.t("dialog.confirm_remove")} <strong>${this.removingCode.name}</strong>?</p>
                        <p style="margin-top: 12px; color: var(--text-secondary); font-size: 14px;">
                            ${this.t("dialog.remove_description", { slot: this.removingCode.slot })}
                        </p>
                    </div>
                    <div class="dialog-actions">
                        <button class="btn btn-secondary" @click=${this._closeRemoveDialog}>${this.t("dialog.cancel")}</button>
                        <button class="btn btn-danger" @click=${this._handleRemove}>${this.t("dialog.remove")}</button>
                    </div>
                </div>
            </div>
        `;
    }

    _onTypeChange(e) {
        const expiryGroup = this.shadowRoot.getElementById("expiry-group");
        if (expiryGroup) {
            expiryGroup.style.display = e.target.value === "guest" ? "block" : "none";
        }
    }

    async _openAddDialog() {
        try {
            const result = await this.hass.callWS({ type: "nimlykoder/suggest_slots", count: 1 });
            this.suggestedSlot = result.slots && result.slots.length > 0 ? result.slots[0] : null;
        } catch (err) {
            console.error("Failed to fetch suggested slot:", err);
            this.suggestedSlot = null;
        }
        this.showAddDialog = true;
    }

    _closeAddDialog() { this.showAddDialog = false; this.suggestedSlot = null; }
    _closeEditDialog() { this.showEditDialog = false; this.editingCode = null; this.editFormError = null; }
    _closeRemoveDialog() { this.showRemoveDialog = false; this.removingCode = null; }

    async _handleAddSubmit() {
        const name = this.shadowRoot.getElementById("add-name").value;
        const pinCode = this.shadowRoot.getElementById("add-pin").value;
        const codeType = this.shadowRoot.getElementById("add-type").value;
        const expiry = this.shadowRoot.getElementById("add-expiry").value;
        const slot = this.shadowRoot.getElementById("add-slot").value;

        if (!name || !pinCode) {
            this.error = "Please fill in all required fields";
            return;
        }

        const data = { name, pin_code: pinCode, code_type: codeType };
        if (expiry) data.expiry = expiry;
        if (slot) data.slot = parseInt(slot);

        try {
            await this.hass.callWS({ type: "nimlykoder/add", ...data });
            this.showAddDialog = false;
            await this.loadCodes();
        } catch (err) {
            this.error = err.message;
        }
    }

    async _handleEditSubmit() {
        const name = this.shadowRoot.getElementById("edit-name").value;
        const expiryEl = this.shadowRoot.getElementById("edit-expiry");
        const expiry = expiryEl ? expiryEl.value : null;
        const newPin = this.shadowRoot.getElementById("edit-pin").value.trim();

        if (!name || !name.trim()) { this.editFormError = "name_required"; return; }
        if (newPin && !/^[0-9]{4,6}$/.test(newPin)) { this.editFormError = "pin_invalid"; return; }

        try {
            if (name !== this.editingCode.name) {
                await this.hass.callWS({ type: "nimlykoder/update_name", slot: this.editingCode.slot, name: name.trim() });
            }
            if (this.editingCode.type === "guest") {
                const currentExpiry = this.editingCode.expiry || "";
                if (expiry !== currentExpiry) {
                    await this.hass.callWS({ type: "nimlykoder/update_expiry", slot: this.editingCode.slot, expiry: expiry || null });
                }
            }
            if (newPin) {
                this.pendingPinUpdate = { slot: this.editingCode.slot, name: name.trim(), pin_code: newPin };
                this.showEditDialog = false;
                this.showPinConfirmDialog = true;
                return;
            }
            this.showEditDialog = false;
            this.editingCode = null;
            await this.loadCodes();
        } catch (err) {
            this.error = err.message;
        }
    }

    _closePinConfirmDialog() { this.showPinConfirmDialog = false; this.pendingPinUpdate = null; }

    async _confirmPinUpdate() {
        if (!this.pendingPinUpdate) return;
        try {
            await this.hass.callWS({ type: "nimlykoder/update_pin", slot: this.pendingPinUpdate.slot, pin_code: this.pendingPinUpdate.pin_code });
            this.showPinConfirmDialog = false;
            this.pendingPinUpdate = null;
            this.editingCode = null;
            await this.loadCodes();
        } catch (err) {
            this.error = err.message;
        }
    }

    async _handleRemove() {
        try {
            await this.hass.callWS({ type: "nimlykoder/remove", slot: this.removingCode.slot });
            this.showRemoveDialog = false;
            this.removingCode = null;
            await this.loadCodes();
        } catch (err) {
            this.error = err.message;
        }
    }
}

customElements.define("nimlykoder-panel", NimlykoderPanel);
