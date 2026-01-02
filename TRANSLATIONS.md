# Translation System for ResticTray

ResticTray uses Qt's translation system to support multiple languages.

## Current Translations

- **English (en)**: Default language (built-in)
- **German (de)**: Complete translation available

## How Translations Work

The application automatically detects your system locale and loads the appropriate translation:

1. On startup, the app checks your system's language setting
2. If a matching translation file exists, it loads automatically
3. If no translation is found, English (default) is used

## Files

- `restictray/translations/restictray_de.ts` - German translation source (XML format)
- `restictray/translations/restictray_de.qm` - Compiled German translation (binary)
- `compile_translations.py` - Script to compile .ts files to .qm files

## Testing the German Translation

To test the German translation, you can:

### Method 1: Change System Locale
```bash
LANG=de_DE.UTF-8 python3 -m restictray
# or with uv:
LANG=de_DE.UTF-8 uv run restictray
```

### Method 2: Change System Settings
Set your system language to German in your desktop environment settings.

## Adding New Translations

### 1. Create Translation File

Create a new `.ts` file based on `restictray_de.ts`:

```bash
cd restictray/translations
cp restictray_de.ts restictray_fr.ts  # For French, for example
```

### 2. Edit Translations

Open the `.ts` file and translate the strings. The format is:

```xml
<message>
    <source>Original English Text</source>
    <translation>Translated Text</translation>
</message>
```

### 3. Compile Translation

Run the compilation script:

```bash
python3 compile_translations.py
```

Or compile manually:

```bash
/usr/lib/python3/dist-packages/PySide6/lrelease restictray/translations/restictray_fr.ts -qm restictray/translations/restictray_fr.qm
```

### 4. Test

Test your translation by running:

```bash
LANG=fr_FR.UTF-8 python3 -m restictray
# or with uv:
LANG=fr_FR.UTF-8 uv run restictray
```

## Updating Translations

When new strings are added to the application:

1. Update the `.ts` file with new `<message>` entries
2. Add translations for the new strings
3. Recompile using `python3 compile_translations.py`

## Translation Guidelines

- Keep translations concise to fit in UI elements
- Maintain consistency in terminology
- Test translations in the actual UI to ensure they fit properly
- Use formal/informal address consistently (e.g., "Sie" vs "du" in German)

## Language Codes

The translation files use standard language codes:
- `de` - German
- `fr` - French
- `es` - Spanish
- `it` - Italian
- `pt` - Portuguese
- `ru` - Russian
- `ja` - Japanese
- `zh` - Chinese
- etc.

For region-specific variants, use: `de_DE`, `de_AT`, `de_CH`, etc.

## Technical Details

The application uses:
- `QTranslator` for loading translations
- `QLocale.system()` to detect the system language
- `self.tr()` in QWidget-derived classes
- `QCoreApplication.translate()` in non-QWidget classes

Translation files are loaded from: `restictray/translations/restictray_<lang>.qm`
