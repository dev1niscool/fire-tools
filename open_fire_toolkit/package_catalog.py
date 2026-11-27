"""Reviewable optional Fire apps. Profiles apply only to packages found on the tablet."""

_PREVIOUS_STANDARD = {
    'com.amazon.kindle': 'Kindle books',
    'com.amazon.avod': 'Prime Video',
    'com.audible.application.kindle': 'Audible',
    'com.goodreads.kindle': 'Goodreads',
    'com.amazon.mp3': 'Amazon Music',
    'com.amazon.windowshop': 'Amazon Shopping',
    'com.amazon.ava.shopping.android': 'Amazon Shopping (alternate)',
    'com.amazon.photos': 'Amazon Photos',
    'com.amazon.photos.importer': 'Amazon Photos importer',
    'com.amazon.weather': 'Weather',
    'com.amazon.kindle.personal_video': 'Personal Videos',
    'com.amazon.ags.app': 'GameCircle',
    'com.amazon.csapp': 'Amazon customer service',
    'com.amazon.dee.app': 'Amazon Alexa app',
    'com.amazon.alexa.youtube.app': 'Alexa YouTube app',
    'com.kingsoft.office.amz': 'WPS Office',
    'com.android.email': 'Email',
    'com.android.calendar': 'Calendar',
    'com.android.contacts': 'Contacts',
    'com.android.music': 'Music',
}
_PREVIOUS_EXTRA = {
    'com.amazon.client.metrics': 'Amazon client metrics',
    'com.amazon.device.metrics': 'Amazon device metrics',
    'com.amazon.wirelessmetrics.service': 'Wireless metrics',
    'com.amazon.ods.kindleconnect': 'Kindle Connect',
    'com.amazon.venezia': 'Amazon Appstore',
    'com.amazon.whisperplay.service.install': 'Whisperplay service installer',
    'com.amazon.comms.knightmessaging': 'Amazon messaging',
    'com.amazon.tabletsubscriptions': 'Tablet subscriptions',
    'com.amazon.tv.ottssocompanionapp': 'TV single sign-on companion',
}
STOCK_HOME = 'com.amazon.firelauncher'
OFFERS = 'com.amazon.kindle.kso'
UPDATERS = ('com.amazon.device.software.ota', 'com.amazon.device.software.ota.override')

# Windows v46 Complete order. Each row names the first preset that includes the app.
_V46_APPS = (
    ('com.amazon.dee.app', 'Amazon Alexa', 'complete'),
    ('com.amazon.venezia', 'Amazon Appstore', 'complete'),
    ('com.amazon.ags.app', 'Amazon Games', 'standard'),
    ('com.amazon.geo.client.maps', 'Amazon Maps', 'standard'),
    ('com.amazon.mp3', 'Amazon Music', 'standard'),
    ('com.amazon.kindle', 'Amazon Newsstand (Kindle)', 'standard'),
    ('com.amazon.avod', 'Amazon Prime Video', 'standard'),
    ('com.amazon.alexa.youtube.app', 'Amazon YouTube', 'standard'),
    ('com.audible.application.kindle', 'Audible', 'standard'),
    ('com.android.calculator2', 'Calculator', 'complete'),
    ('com.android.calendar', 'Calendar', 'complete'),
    ('com.android.camera2', 'Camera', 'complete'),
    ('com.android.deskclock', 'Clock', 'complete'),
    ('com.android.contacts', 'Contacts', 'complete'),
    ('com.amazon.zico', 'Docs', 'complete'),
    ('com.amazon.smartgenie', 'Device Dashboard', 'standard'),
    ('com.amazon.kindle.otter.oobe', 'Device Setup', 'complete'),
    ('com.android.email', 'Email', 'complete'),
    ('com.amazon.tahoe', 'FreeTime (Amazon Kids)', 'complete'),
    ('com.goodreads.kindle', 'Goodreads', 'standard'),
    ('com.amazon.csapp', 'Help', 'standard'),
    ('com.amazon.imdb.tv.mobile.app', 'IMDb TV', 'complete'),
    ('com.amazon.webapp', 'Kindle Store', 'standard'),
    ('com.amazon.ods.kindleconnect', 'Mayday Sharing', 'standard'),
    ('org.mopria.printplugin', 'Mopria Print Service', 'standard'),
    ('com.android.music', 'Music', 'standard'),
    ('com.amazon.kindle.personal_video', 'My Videos', 'standard'),
    ('com.amazon.iris', 'News', 'standard'),
    ('com.amazon.photos.importer', 'Photo Importer', 'standard'),
    ('com.amazon.photos', 'Prime Photos (Amazon Photos)', 'standard'),
    ('com.amazon.windowshop', 'Shop Amazon', 'standard'),
    ('com.amazon.cloud9', 'Silk Browser', 'complete'),
    ('com.kingsoft.office.amz', 'WPS Office', 'standard'),
    ('com.washingtonpost.rainbow', 'Washington Post', 'standard'),
    ('com.amazon.weather', 'Weather', 'standard'),
)
_STANDARD = tuple(p for p, _, first_profile in _V46_APPS if first_profile == 'standard')
_COMPLETE = tuple(row[0] for row in _V46_APPS)
DEBLOAT_PROFILES = {
    'standard': _STANDARD, 'complete': _COMPLETE,
    'standard-v0.2': tuple(_PREVIOUS_STANDARD), 'complete-v0.2': (*_PREVIOUS_STANDARD, *_PREVIOUS_EXTRA),
}
DEBLOAT_TITLES = {
    'standard': 'Standard Debloat (Recommended)', 'complete': 'Complete Debloat',
    'custom': 'Load From File...',
    'standard-v0.2': 'Standard Debloat (v0.2)', 'complete-v0.2': 'Complete Debloat (v0.2)',
}
DEBLOAT_RESTORE_DESCRIPTION = (
    'Restore Everything enables eligible disabled apps from Complete Debloat for owner user 0, '
    'including apps disabled before debloating. Undo restores the owner states saved for the last package change.'
)
DEBLOAT_COMPLETE_WARNING = (
    'Complete Debloat includes the Amazon Appstore, Alexa, Silk Browser, Camera and Email. '
    'Changing their availability can interrupt app downloads, browsing and other tablet features.'
)
APP_LABELS = {
    **_PREVIOUS_STANDARD, **_PREVIOUS_EXTRA, **{p: label for p, label, _ in _V46_APPS},
    STOCK_HOME: 'Fire Launcher', OFFERS: 'Special Offers',
    UPDATERS[0]: 'Fire OS updater', UPDATERS[1]: 'Fire OS updater override',
}

# Older releases allowed these services in package batches. An existing undo
# record may still need to reinstall or re-enable one for the owner.
PROTECTED_SERVICES = {
    'com.amazon.application.compatibility.enforcer': 'Update compatibility checker',
    'com.amazon.appverification': 'App verification (Device Scan)',
    'com.amazon.cloud9.systembrowserprovider': 'System browser provider',
    'com.amazon.imp': 'Identity Mobile Platform',
    'com.amazon.logan': 'VoiceView screen reader',
    'com.amazon.securitysyncclient': 'Security sync client',
    'com.android.carrierconfig': 'Carrier configuration',
}
_CORE = {
    'android', 'com.android.phone', 'com.android.bluetooth', 'com.android.shell',
    'com.android.systemui', 'com.android.settings', 'com.android.server.telecom',
    'com.android.externalstorage', 'com.android.documentsui', 'com.android.keychain',
    'com.android.inputdevices', 'com.android.managedprovisioning', 'com.android.adbd',
    'com.android.location.fused', 'com.android.storagemanager', 'com.android.sharedstoragebackup',
    'com.android.proxyhandler', 'com.android.captiveportallogin', 'com.android.credentialmanager',
    'com.google.android.documentsui', 'com.amazon.device.settings', 'com.amazon.h2settingsfortablet',
    'com.amazon.kindle.rdmdeviceadmin', 'com.amazon.parentalcontrols', 'com.amazon.pm',
    'com.amazon.platform', 'com.amazon.fireinputdevices', 'com.amazon.identity.auth.device.authorization',
    'com.amazon.tv.launcher', STOCK_HOME, OFFERS, *UPDATERS, *PROTECTED_SERVICES,
}
_CORE_TREES = (
    'com.android.providers', 'com.amazon.providers', 'com.google.android.providers',
    'com.android.networkstack', 'com.google.android.networkstack', 'com.android.inputmethod',
    'com.amazon.kindle.otter.oobe', 'com.android.settings', 'com.android.systemui',
    'com.amazon.device.settings', 'com.android.packageinstaller', 'com.google.android.packageinstaller',
    'com.amazon.packageinstaller', 'com.android.permissioncontroller', 'com.google.android.permissioncontroller',
    'com.android.setupwizard', 'com.google.android.setupwizard', 'com.android.launcher',
    'com.android.launcher3', 'jp.co.omronsoft.iwnnime', 'com.amazon.platform',
)


def is_protected(package: str) -> bool:
    return package in _CORE or any(package == root or package.startswith(root + '.') for root in _CORE_TREES)


def canonical_debloat_profile(profile: str) -> str:
    return 'standard' if profile == 'recommended' else profile


def debloat_plan_title(profile: str, mode: str) -> str:
    profile = canonical_debloat_profile(profile)
    title = 'Custom package list' if profile == 'custom' else DEBLOAT_TITLES[profile]
    if mode == 'enable':
        return 'Restore Everything' if profile == 'complete' else f'Enable apps — {title}'
    if mode == 'uninstall':
        return f'Remove apps for owner — {title}'
    return title


def package_display_name(package: str) -> str:
    label = APP_LABELS.get(package) or PROTECTED_SERVICES.get(package)
    return f'{label} ({package})' if label else package


def debloat_preset_comparison() -> str:
    extras = tuple(p for p in _COMPLETE if p not in _STANDARD)
    eligible = sum(not is_protected(p) for p in _COMPLETE)
    lines = [f'{DEBLOAT_TITLES["standard"]} — {len(_STANDARD)} packages shared with Complete']
    lines.extend(package_display_name(p) for p in _STANDARD)
    lines.extend(('', f'{DEBLOAT_TITLES["complete"]} — {len(_COMPLETE)} packages, up to {eligible} eligible',
                  f'{len(extras)} additions to Standard'))
    for p in extras:
        detail = ' — kept (protected)' if is_protected(p) else ''
        lines.append(package_display_name(p) + detail)
    return '\n'.join((*lines, '', DEBLOAT_RESTORE_DESCRIPTION))
