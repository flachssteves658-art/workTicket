from __future__ import annotations

LANGUAGES = {
    'en-GB': {
        'warning_people_in_controlled_area':
            'Warning: {count} people have entered the controlled area!',
        'warning_no_hardhat':
            'Warning: {count} people are not wearing a hardhat!',
        'warning_no_safety_vest':
            'Warning: {count} people are not wearing a safety vest!',
        'warning_close_to_machinery':
            'Warning: {count} people are too close to machinery!',
        'warning_close_to_vehicle':
            'Warning: {count} people are too close to vehicles!',
        'warning_people_in_utility_pole_controlled_area':
            'Warning: {count} people have entered the utility pole '
            'restricted area!',
        'detect_machinery_close_to_pole':
            'Warning: {count} machineries are too close to the utility pole!',

        'no_warning': 'No warning',
        'machinery': 'machinery',
        'vehicle': 'vehicles',
        'helmet': 'helmet',
        'person': 'person',
        'no_helmet': 'no helmet',
        'vest': 'safety vest',
        'no_vest': 'no safety vest',
        # 'mask': 'mask',
        # 'no_mask': 'no mask',
        'cone': 'cone',

        'warning_notification': '[Warning Notification]',
    },

    'zh-CN': {
        'warning_people_in_controlled_area':
            '警告: 有{count}个人进入受控区域!',
        'warning_no_hardhat':
            '警告: 有{count}人未佩戴安全帽!',
        'warning_no_safety_vest':
            '警告: 有{count}人未穿着安全背心!',
        'warning_close_to_machinery':
            '警告: 有{count}人过于靠近机械!',
        'warning_close_to_vehicle':
            '警告: 有{count}人过于靠近车辆!',
        'warning_people_in_utility_pole_controlled_area':
            '警告: 有{count}人进入电桿管制区!',
        'detect_machinery_close_to_pole':
            '警告: 有{count}个机械过于靠近电桿!',

        'no_warning': '无警告',
        'machinery': '机械',
        'vehicle': '车辆',
        'helmet': '安全帽',
        'person': '人员',
        'no_helmet': '无安全帽',
        'vest': '安全背心',
        'no_vest': '无安全背心',
        # 'mask': '口罩',
        # 'no_mask': '无口罩',
        'cone': '安全锥',

        'warning_notification': '[警示通知]',
    },
}


class Translator:
    """
    A class to handle translations based on the provided language.
    """

    @staticmethod
    def translate_from_dict(
        body_dict: dict[str, dict[str, int]],
        language: str,
    ) -> list[str]:
        """
        Translate a dictionary of warning messages into the specified language.

        Example:
            body_dict = {
                "warning_close_to_vehicle": {"count": "3"},
                "warning_no_safety_vest": {}
            }
            language = "zh-TW"

            => [
                "警告: 有3人過於靠近車輛!",
                "警告: 有人沒有穿安全背心!"
            ]

        Args:
            body_dict (dict[str, dict[str, int]]):
                A dictionary where each key corresponds to a warning message
                and its value is a dictionary of placeholders to be replaced.
            language (str):
                The locale code (e.g. "en-GB", "zh-TW") to use.

        Returns:
            list[str]: A list of translated warning messages.
        """
        # If the language key is not in LANGUAGES, default to 'en-GB'
        if language not in LANGUAGES:
            language = 'en-GB'

        translations: list[str] = []
        lang_map = LANGUAGES[language]

        for key, placeholders in body_dict.items():
            template = lang_map.get(key)
            if not template:
                # If the key has no template, use the key itself as the message
                translations.append(key)
                continue

            msg = template
            # Replace placeholders like {count} in the template
            for ph_key, ph_value in placeholders.items():
                msg = msg.replace(f"{{{ph_key}}}", str(ph_value))

            translations.append(msg)

        return translations


def main() -> None:
    """
    Simple demonstration of the Translator class's translate_from_dict method.
    """
    body_dict = {
        'warning_no_hardhat': {'count': 2},
        'warning_no_safety_vest': {'count': 1},
        'warning_people_in_utility_pole_controlled_area': {'count': 3},
    }
    language = 'en-GB'

    translations = Translator.translate_from_dict(body_dict, language)
    print(translations)
    # Possible output:
    # [
    #   "Warning: 2 people are not wearing a hardhat!",
    #   "Warning: 1 people are not wearing a safety vest!",
    #   "Warning: 3 people have entered the utility pole restricted area!"
    # ]


if __name__ == '__main__':
    main()
