"""Reviewable optional Fire apps. Profiles apply only to packages found on the tablet."""

STANDARD = {
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
EXTRA = {
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
DEBLOAT_PROFILES = {'standard': tuple(STANDARD), 'complete': (*STANDARD, *EXTRA)}
APP_LABELS = {**STANDARD, **EXTRA, STOCK_HOME: 'Fire Launcher', OFFERS: 'Special Offers',
              UPDATERS[0]: 'Fire OS updater', UPDATERS[1]: 'Fire OS updater override'}

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
    'com.amazon.tv.launcher', STOCK_HOME, OFFERS, *UPDATERS,
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
