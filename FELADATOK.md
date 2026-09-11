# A képkonverter feladatai

A 2026-09-12-i konzisztencia-ellenőrzés megállapításai alapján. Az ellenőrzés a konverterre, a grafikus indítóra, az indító segédfájlokra és a dokumentációra terjedt ki. Az elkészült részfeladatokat pipa jelzi; az „Igazolt probléma” bekezdések az eredeti ellenőrzés állapotát írják le.

## 1. Elsődleges javítások

### Felülírásvédelem

- [x] A konverzió előtt ellenőrizni, hogy a forrás és a cél ugyanaz a fájl-e; az eredeti kép véletlen felülírását megakadályozni.
- [x] A már létező célfájlokra és a feldolgozáson belüli névütközésekre egységes szabályt kialakítani, például kihagyást vagy egyedi név képzését, egyértelmű visszajelzéssel.
- [x] Kezelni a külön mappákból származó azonos nevű képeket és az azonos törzsnevű JPG/JPEG bemeneteket.

**Igazolt probléma:** ha a célmappa a forrásmappa, a kimenet JPG, és nincs elő-/utótag, az eredeti JPG felülíródik. Két külön mappa `same.jpg` fájljából közös célmappában csak a második eredmény maradt meg. A `kep.jpg` és `kep.jpeg` célneve szintén ütközik.

**Elfogadás:** egyik esetben sem történik jelzés nélküli felülírás, és az eredeti kép megmarad.

Érintett kód: [KepKonvForFilesOrDirs.py](KepKonvForFilesOrDirs.py), `process_directory`, `main`, `convert_image`.

### Konverziós hibák kezelése

- [x] Ellenőrizni minden ImageMagick-hívás visszatérési kódját.
- [x] Dátummásolást csak sikeres konverzió után végezni.
- [x] Sikertelen konverziónál kihagyni a dátummásolást a korábbról létező célfájlra is.
- [x] A feldolgozás végén összesíteni a sikeres, sikertelen és kihagyott bemeneteket.
- [x] Egyértelműen jelezni a hiányzó külső programot és a fájlonkénti feldolgozási hibákat.

**Igazolt probléma:** sikertelen konverzió után is elindul a dátummásolás. A „Feldolgozás vége” üzenet nem tájékoztat az eredményről.

**Elfogadás:** hibás bemenetnél nincs dátummásolás, a hiba szerepel az összesítésben, és egy régi célfájl dátumai változatlanok maradnak.

Érintett kód: `convert_image`, `main`.

### Dátummegőrzés

- [x] Megszüntetni az AVIF EXIF-írását feltétel nélkül letiltó ágat és javítani a hozzá tartozó téves üzenetet.
- [x] AVIF esetén is megkísérelni a dátumok másolását, a tényleges eszköztámogatás és eredmény alapján kezelve a hibákat.
- [x] Pontosan meghatározni és a felületen leírni, mely EXIF- és fájlrendszer-időpontokra vonatkozik a dátummegőrzés.
- [x] Egységesíteni a kikapcsolt dátummegőrzés jelentését: minden módban a külön másolást mellőzi, nem töröl metaadatokat.
- [x] Egyértelműen jelezni, hogy a fájlrendszer szerinti létrehozási idő nem része a megőrzésnek.
- [x] Felülvizsgálni a dátumokra és a WebP EXIF-támogatására vonatkozó kódbeli magyarázatokat.
- [x] Egyetlen, folyamatosan futó ExifToolt használni a teljes feldolgozáshoz, leállítási és parancsidő-korláttal.
- [x] A fájl módosítási idejét a valódi EXIF készítési időből beállítani; hiányzó készítési dátumnál figyelmeztetni, helyettesítő fotózási dátum kitalálása nélkül.
- [x] Megőrizni az időzónát és a másodperctöredéket, és jelezni a hiányzó időzóna miatti helyi értelmezést.
- [x] Dátumkezelési összesítést készíteni és a Windows által kiolvasott dátumokat ellenőrizni.

**Megvalósítás és mérés:** [photo_dates.py](photo_dates.py); a [tesztek](test_photo_dates.py) JPG és PNG forrásból mindhárom módot és mindhárom kimeneti formátumot ellenőrzik. A 20 kis képes dátumkezelési mérés 1,01 másodpercet adott a korábbi 13,40 másodperc helyett. A Windows a helyi próbában csak a JPG EXIF készítési idejét olvasta ki, ezért WebP/AVIF esetén az egységes rendezéshez a „Módosítás dátuma” oszlop használata dokumentált.

**Igazolt problémák:**

- Normál módban, bekapcsolt megőrzés mellett az AVIF-ből hiányzott a `DateTimeOriginal`, miközben a mellékelt ExifTool közvetlenül sikeresen átmásolta ugyanabba a fájlba.
- Kikapcsolt megőrzés mellett a JPG fotózási dátuma normál módban eltűnt, crop és contain módban megmaradt. Az ágak eltérően használnak `-thumbnail`, illetve `-resize` műveletet.
- Az `os.utime` hívások a hozzáférési és módosítási időt állítják, a fájlrendszer szerinti létrehozási időt nem.

**Elfogadás:** ismert fotózási dátumú képpel mindhárom módban és mindhárom formátumban ellenőrzött, dokumentált eredmény születik bekapcsolt és kikapcsolt megőrzés mellett is.

Érintett kód: `convert_image`, `set_all_dates_from_file`, `main`.

## 2. Opciók és visszajelzések egységesítése

### Bemeneti értékek ellenőrzése

- [ ] A szélességet és magasságot pozitív egész számként ellenőrizni.
- [ ] A minőség megengedett tartományát meghatározni, kiírni és ellenőrizni.
- [ ] A mód-, formátum- és igen/nem-választásnál egységes szóközlevágást és kisbetűsítést alkalmazni.
- [ ] Hibás választásnál csendes alapértékre váltás helyett újrakérdezni.
- [ ] A háttérszín súgójában a hibás `#gghh22` példát érvényesre, például `#aabb22` értékre cserélni, és az érvénytelen színeket kezelni.

**Igazolt probléma:** az `abc` szélesség, `0` magasság és `999` minőség ellenőrzés nélkül továbbjutott. A `C` normál módot, a `J` WebP kimenetet eredményezett, az `i ` pedig kikapcsolta a dátummegőrzést.

Érintett kód: `get_input`, `main`.

### Célmappa

- [x] Üres célmappánál a tényleges kimeneti almappát megjeleníteni az „eredeti helyükön maradnak” üzenet helyett.
- [x] Az `opt-webp-or-jpg` elnevezést az AVIF-támogatással összhangba hozni, vagy dokumentálni a rögzített nevet.

Érintett kód: `main`, `process_directory`.

### Előtag, utótag és fájlnév

- [ ] Üres vagy csak szóközt tartalmazó `prefix.txt` és `suffix.txt` esetén üres elő-/utótagot használni.
- [ ] Egyértelművé tenni, hogy az üres globális elő-/utótag a helyi szövegfájlok használatát engedi, és biztosítani a helyi értékek kifejezett mellőzését is.
- [x] Egységesíteni vagy dokumentálni a PNG-re alkalmazott külön névképzési szabályt: `kep.png.webp`, szemben a JPG/JPEG bemenet `kep.webp` célnevével.
- [x] A névképzési szabályokat összehangolni a felülírásvédelemmel.

**Igazolt probléma:** üres elő-/utótagfájlok mellett a függvény `('-', '-')` értéket ad vissza, így például `-kep-.webp` keletkezik.

Érintett kód: `get_prefix_suffix`, `convert_image`, `process_directory`, `main`.

### Bemeneti fájlok és mappák

- [x] A támogatott bemeneti formátumokat feltüntetni: jelenleg JPG, JPEG és PNG.
- [x] A nem támogatott fájlokat és a nem létező útvonalakat indoklással kihagyottként jelezni.
- [x] Mappafeldolgozásnál ellenőrizni, hogy a kiválasztott bejegyzés valóban fájl-e.
- [x] Egyértelművé tenni, hogy a mappafeldolgozás jelenleg nem rekurzív.
- [ ] Eldönteni, szükséges-e a WebP/AVIF bemenet vagy a rekurzív feldolgozás támogatása; ezek jelenleg nem elérhető funkciók.

**Igazolt probléma:** egy `fake.jpg` nevű mappa is konvertálásra került volna. A WebP/AVIF bemenet és a nem létező útvonal figyelmeztetés nélkül kimarad.

Érintett kód: `process_directory`, `main`.

## 3. Méretezés és kódolás

- [x] Az opciók változtatása nélkül párhuzamosítani a képkonverziót: ezen a gépen legfeljebb 3 kép, képenként 2 ImageMagick-szál.
- [x] Korlátozni a folyamatok és a munkasor méretét, valamint a párhuzamos pixelgyorsítótárak memóriahasználatát.
- [x] A fő szálon, sorosan tartani az egyetlen közös ExifTool használatát.
- [x] Az egész bemeneti lista célneveit ellenőrizni indítás előtt, és ideiglenes kimenettel megakadályozni a részleges fájlok véglegesítését.
- [x] A képi eredményt összevetni a korábbi parancsokkal mindhárom módban, JPG/PNG bemenettel és JPG/WebP/AVIF kimenettel.

**Mérés bekapcsolt dátummegőrzéssel:** 6 darab 4000×3000-es mesterséges JPEG, 3840×2160 normál mód, 75-ös minőség: JPG 4,10 → 2,45 mp (1,68×); WebP 6,71 → 3,30 mp (2,04×). A soros és párhuzamos kimenetek bájtról bájtra megegyeztek. A [párhuzamos tesztek](test_parallel_conversion.py) ellenőrzik a névütközést, a csak fő szálon végzett dátummásolást, a hibás képeket és az időközben létrejövő célfájl védelmét is.


- [ ] A módválasztásnál jelezni a nagyítás eltérő működését.
- [ ] Eldönteni, hogy a nagyítás maradjon-e módhoz kötött, vagy kapjon külön, egységes opciót.
- [ ] Az AVIF külön kódolási paramétereit egységesen alkalmazni, vagy indokolni és dokumentálni a módok közötti eltérést. Jelenleg csak normál módban szerepelnek.

A jelenlegi, mindhárom kimeneti formátummal ellenőrzött működés:

| Mód | Művelet | 40×20-as bemenet, 100×100-as cél |
| --- | --- | --- |
| `n` – normal | Arányos beillesztés, nagyítás nélkül | 40×20 |
| `c` – crop | Kitöltés, középre igazított vágás, szükség esetén nagyítás | 100×100 |
| `t` – contain | Arányos beillesztés, háttérkitöltés, szükség esetén nagyítás | 100×100 |

Érintett kód: `convert_image`, `main`.

## 4. Indítás és dokumentáció

- [ ] Egységesíteni vagy dokumentálni a Python-környezet kiválasztását: a GUI a PATH szerinti `python` parancsot, a BAT és a registry rögzített Python-útvonalat használ.
- [x] A README-t frissíteni mindhárom módra és mindhárom kimeneti formátumra.
- [x] Dokumentálni a támogatott bemeneteket, az alapértelmezett célmappát, a fájlnévképzést, a nagyítást és a dátummegőrzés pontos jelentését.
- [x] A használati példában a helyőrző scriptnév helyett a tényleges `KepKonvForFilesOrDirs.py` nevet használni.
- [ ] A javítások után összehangolni a súgószövegeket, a konzolüzeneteket és a README-t.

Érintett fájlok: [app.py](app.py), [BAT indító](KepKonvForFilesOrDirs-SendTo.bat), [registry-beállítások](KepKonvForFilesOrDirs.reg), [README.md](README.md).

## Ellenőrzési alap

Az áttekintés során ideiglenes próbaképekkel ellenőrzött esetek:

- Mind a kilenc méretezési mód–kimeneti formátum kombináció létrehozta a várt méretű képet.
- Eredeti JPG felülírása és külön mappák azonos nevű képeinek ütközése.
- Sikertelen konverzió utáni dátummásolási hívás.
- Dátummegőrzés kikapcsolásának eltérő hatása JPG-kimenetnél a három módban.
- Bekapcsolt dátummegőrzés JPG, WebP és AVIF kimenetnél normál módban; közvetlen AVIF EXIF-írás a mellékelt ExifToollal.
- Üres elő-/utótagfájlok, hibás opcióértékek és képkiterjesztésű mappa kezelése.
- Mindkét Python-forrás szintaktikai ellenőrzése.

Ez az ellenőrzés nem jelent minden kép- és metaadatváltozatra kiterjedő tesztelést. A javítások elfogadásakor a fenti hibákat célzottan újra kell ellenőrizni.

Külső referencia: [ExifTool – támogatott fájltípusok és használat](https://exiftool.org/exiftool_pod2.html).
