"""Display names for the build models in Amazon's Fire tablet specifications.

Source: https://developer.amazon.com/docs/device-specs/ft-identify-tablet-devices.html
"""

from .adb import DeviceInfo


_BUILD_MODELS = {
    "KFRASWI": "Fire HD 8 (2024, 12th gen)",
    "KFTUWI": "Fire HD 10 (2023, 13th gen)",
    "KFSNWI": "Fire Max 11 (2023, 13th gen)",
    "KFRAWI": "Fire HD 8 (2022, 12th gen)",
    # Amazon lists the same 3 GB build model for both releases.
    "KFRAPWI": "Fire HD 8 (2022 or 2024, 12th gen)",
    "KFQUWI": "Fire 7 (2022, 12th gen)",
    "KFTRWI": "Fire HD 10 (2021, 11th gen)",
    "KFTRPWI": "Fire HD 10 (2021, 11th gen)",
    "KFONWI": "Fire HD 8 (2020, 10th gen)",
    "KFMAWI": "Fire HD 10 (2019, 9th gen)",
    "KFMUWI": "Fire 7 (2019, 9th gen)",
    "KFKAWI": "Fire HD 8 (2018, 8th gen)",
    "KFSUWI": "Fire HD 10 (2017, 7th gen)",
    "KFDOWI": "Fire HD 8 (2017, 7th gen)",
    "KFAUWI": "Fire 7 (2017, 7th gen)",
    "KFGIWI": "Fire HD 8 (2016, 6th gen)",
    "KFTBWI": "Fire HD 10 (2015, 5th gen)",
    "KFMEWI": "Fire HD 8 (2015, 5th gen)",
    "KFFOWI": "Fire (2015, 5th gen)",
    "KFSAWA": "Fire HDX 8.9 (2014, 4th gen)",
    "KFSAWI": "Fire HDX 8.9 (2014, 4th gen)",
    "KFASWI": "Fire HD 7 (2014, 4th gen)",
    "KFARWI": "Fire HD 6 (2014, 4th gen)",
    "KFTHWA": "Kindle Fire HDX 7 (2013, 3rd gen)",
    "KFTHWI": "Kindle Fire HDX 7 (2013, 3rd gen)",
    "KFAPWA": "Kindle Fire HDX 8.9 (2013, 3rd gen)",
    "KFAPWI": "Kindle Fire HDX 8.9 (2013, 3rd gen)",
    "KFSOWI": "Kindle Fire HD 7 (2013, 3rd gen)",
    "KFOT": "Kindle Fire (2012, 2nd gen)",
    "KFTT": "Kindle Fire HD 7 (2012, 2nd gen)",
    "KFJWA": "Kindle Fire HD 8.9 (2012, 2nd gen)",
    "KFJWI": "Kindle Fire HD 8.9 (2012, 2nd gen)",
    "Kindle Fire": "Kindle Fire (2011, 1st gen)",
}


def tablet_product_name(device: DeviceInfo) -> str | None:
    if device.manufacturer.strip().casefold() != "amazon":
        return None
    return _BUILD_MODELS.get(device.model)
