import numpy as np
import pandas as pd
import jsonlines
import os
import warnings
from datetime import datetime 
import json
import re
from langdetect import detect
from googletrans import Translator
import random
import sys
import math

pd.set_option('display.max_rows', 50)
warnings.filterwarnings("ignore", category=pd.errors.DtypeWarning)

def main(chunk_size, file_id, project_path):
    print("\n\n01_preprocessing \n")
    print("chunk_size:", chunk_size)
    print("File ID:", file_id)
    print("Project Path:", project_path)
    chunk_size = int(chunk_size)

    # configuration
    jsonl_00 = project_path + "data/" + file_id + "_openfoodfacts_00" + ".jsonl" # fichier sans aucune étape de prétraitement (dézipé) 
    jsonl_01 = project_path + 'data/' + file_id + '_openfoodfacts_01.jsonl' # fichier avec première étape de prétraitement (uniquement colonnes intéressantes)
    jsonl_02 = project_path + 'data/' + file_id + '_openfoodfacts_02.jsonl' # fichier avec deuxième étape de prétraitement (traitement intégral)
    jsonl_03 = project_path + 'data/' + file_id + '_openfoodfacts_03.jsonl' # fichier avec troisième étape de prétraitement, mélange des lignes aléatoirement
    jsonl_04 = project_path + 'data/' + file_id + '_openfoodfacts_04.jsonl' # suppression des None et none par des NaN
    train = project_path + "data/" + file_id + "_train" + ".jsonl"
    test = project_path + "data/" + file_id + "_test" + ".jsonl"
    valid = project_path + "data/" + file_id + "_valid" + ".jsonl"
    jsonl_sample = project_path + 'data/' + file_id + '_openfoodfacts_sample.jsonl'
    col_to_keep = ['pnns_groups_1',
                'ingredients_tags',
                'packaging',
                'product_name',
                'ecoscore_tags',
                'categories_tags',
                'ecoscore_score',
                'labels_tags',
                'code',
                'countries']


    # récupérer la date du jour 
    current_date_time = datetime.now()
    date_format = "%d/%m/%Y %H:%M:%S.%f"
    start_date = current_date_time.strftime("%d/%m/%Y %H:%M:%S.%f")[:-3]
    date_code = current_date_time.strftime('%d%m%Y%H%M%S') + f"{current_date_time.microsecond // 1000:03d}"


    def add_logs(logData):
        print(logData)
        with open(f"{project_path}logs/01_preprocessing_{date_code}_logs.txt", "a") as logFile:
            logFile.write(f'{logData}\n')

    def get_time():
        current_date = datetime.now()
        current_date = current_date.strftime("%d/%m/%Y %H:%M:%S.%f")[:-3]
        return current_date


    def count_chunks(file_path, chunk_size):
        with open(file_path, 'r') as file:
            line_count = sum(1 for _ in file)
        total_chunks = (line_count + chunk_size - 1) // chunk_size
        return total_chunks


    def delete_file(file_path):
        if os.path.exists(file_path):
            os.remove(file_path)
            add_logs(f"file deleted: {file_path}")
        else:
            add_logs(f"ERROR, does not exists: {file_path}")


    # génération jsonl filtré
    def jsonl_filtered_creator(origin_file):
        with open(origin_file, 
                'r', 
                encoding='utf-8') as infile, open(jsonl_01, 'w', 
                                                    encoding='utf-8') as outfile:
            buffer = []
            
            for i, line in enumerate(infile):
                record = json.loads(line.strip())        
                filtered_record = {key: record.get(key) for key in col_to_keep}        
                buffer.append(json.dumps(filtered_record) + '\n')
                
                if len(buffer) >= chunk_size:
                    outfile.writelines(buffer)
                    buffer = []
            
            if buffer:
                outfile.writelines(buffer)
        add_logs(f"jsonl filtered generated: {origin_file}")


    # création d'un échantillion (mini jsonl) pour inspecter la qualité des données
    def jsonl_sample_creator(file_to_sample, jsonl_sample, num_samples=60):
        add_logs(f"sampling {num_samples} random lines from {file_to_sample} to {jsonl_sample}")
        with open(file_to_sample, 'r') as infile:
            total_lines = sum(1 for _ in infile)
        add_logs(f"total number of lines jsonl, 02: {total_lines}")
        sample_indices = random.sample(range(total_lines), num_samples)
        with open(file_to_sample, 'r') as infile, open(jsonl_sample, 'w') as outfile:
            for current_line_number, line in enumerate(infile):
                if current_line_number in sample_indices:
                    outfile.write(line)
        add_logs(f"jsonl sample created: {jsonl_sample}")


    def main_processing(jsonl_01, jsonl_02):
        # traducteur, remplace le contenu d'une autre langue que l'anglais en anglais 
        translator = Translator()
        
        def translate_to_english(text):
            if text is np.nan:
                return text
            try:
                detected_lang = detect(text)
                if detected_lang == 'en':
                    return text.lower()
                else:
                    translated = translator.translate(text, dest='en')
                    return translated.text.lower()
            except Exception as e:
                return text
            
        def process_chunk(chunk):
            df = chunk.copy()

            # renommer les colonnes
            df.rename(columns={'pnns_groups_1': 'groups'}, inplace=True)
            df.rename(columns={'ingredients_tags': 'ingredients_temp'}, inplace=True)
            df.rename(columns={'product_name': 'name'}, inplace=True)
            df.rename(columns={'ecoscore_tags': 'ecoscore_groups'}, inplace=True)
            df.rename(columns={'categories_tags': 'categories_temp'}, inplace=True)
            df.rename(columns={'ecoscore_score': 'ecoscore_note'}, inplace=True)
            df.rename(columns={'labels_tags': 'labels_temp'}, inplace=True)


            # traitement col GROUPS 
            df['groups'] = df['groups'].replace("unknown", np.nan, regex=False)
            df['groups'] = df['groups'].str.lower() 
            #df['groups'] = df['groups'].apply(translate_to_english)


            # traitement col NAME
            df['name'] = df['name'].replace("", np.nan)  
            df['name'] = df['name'].str.lower()
            #df['name'] = df['name'].apply(translate_to_english)


            # traitement col CODE
            df['code'] = df['code'].replace("", np.nan)  
            df['code'] = pd.to_numeric(df['code'], errors='coerce')
            df['code'] = df['code'].apply(lambda x: np.nan if pd.isna(x) else int(round(x)))


            # supprime les lignes où le code unique ou le nom produit sont absents 
            df = df[df['name'].notna() & df['code'].notna()]


            # traitement col INGREDIENTS
            df['ingredients_temp'] = df['ingredients_temp'].replace("", np.nan)  # remplace vide par np.nan
            df['ingredients_temp'] = df['ingredients_temp'].apply(lambda x: x if isinstance(x, list) else []) # remplace np.nan par liste vide 
            df['ingredients_temp'] = df['ingredients_temp'].apply(lambda x: ', '.join(x)) # converti liste en string 
            # extraire éléments avec 'en:' nouvelle colonne
            def extract_en_ingredients(ingredient_list):
                ingredients = ingredient_list.strip('[]').split(', ')
                return [ingredient.split(':')[-1] for ingredient in ingredients if ingredient.startswith('en:')] 
            df['ingredients'] = df['ingredients_temp'].apply(extract_en_ingredients)
            df.drop(columns=['ingredients_temp'], inplace=True)
            df['ingredients'] = df['ingredients'].apply(lambda x: ', '.join(x))
            df['ingredients'] = df['ingredients'].replace("", np.nan)  
            #df['ingredients'] = df['ingredients'].apply(translate_to_english)


            # traitement col PACKAGING
            df['packaging'] = df['packaging'].replace("", np.nan)
            def remove_two_letters_and_colon(s):
                if isinstance(s, str):
                    return re.sub(r'\b\w{2}:\b', '', s)
                return s
            df['packaging'] = df['packaging'].apply(remove_two_letters_and_colon)
            df['packaging'] = df['packaging'].astype(str)
            df['packaging'] = df['packaging'].str.lower()
            #df['packaging'] = df['packaging'].apply(translate_to_english)


            # traitement col ECOSCORE_GROUPS
            df['ecoscore_groups'] = df['ecoscore_groups'].apply(lambda x: ', '.join(x) if isinstance(x, list) else x) # conversion liste vers string 
            df['ecoscore_groups'] = df['ecoscore_groups'].replace("unknown", np.nan)
            df['ecoscore_groups'] = df['ecoscore_groups'].replace("", np.nan)
            df['ecoscore_groups'] = df['ecoscore_groups'].replace("not-applicable", np.nan)


            # traitement col CATEGORIES
            df['categories_temp'] = df['categories_temp'].replace("", np.nan)  
            df['categories_temp'] = df['categories_temp'].apply(lambda x: x if isinstance(x, list) else [])
            df['categories_temp'] = df['categories_temp'].apply(lambda x: ', '.join(x))
            # extraire éléments avec 'en:' nouvelle colonne
            def extract_en_categories(categories_list):
                ingredients = categories_list.strip('[]').split(', ')
                return [ingredient.split(':')[-1] for ingredient in ingredients if ingredient.startswith('en:')]
            df['categories'] = df['categories_temp'].apply(extract_en_categories)
            df.drop(columns=['categories_temp'], inplace=True)
            df['categories'] = df['categories'].apply(lambda x: ', '.join(x))
            df['categories'] = df['categories'].replace("", np.nan)  
            #df['categories'] = df['categories'].apply(translate_to_english)


            # traitment col COUNTRIES
            def clean_abrev(texte):
                if isinstance(texte, str):
                    return re.sub(r'\b\w{2}:\b', '', texte).strip()
                return texte
            country_mapping = {
                'åland': 'finland',
                'european-union': 'europe',
                'cap-vert': 'cape verde',
                'república de china': 'china',
                'sudán': 'sudan',
                'scotland': 'united kingdom',
                'nueva zelanda': 'new zealand',
                'libye': 'libya',
                'великобритания': 'united kingdom',
                'رومانيا': 'romania',
                'burundi': 'burundi',
                'galmudug': 'somalia',
                'østrig': 'austria',
                'holland': 'netherlands',
                'libya': 'libya',
                'bahrain': 'bahrain',
                'islanda': 'iceland',
                'belgica': 'belgium',
                'irsko': 'ireland',
                'βουλγαρία': 'bulgaria',
                'гърция': 'greece',
                'islandia': 'iceland',
                'olanda': 'netherlands',
                'worldwide': 'world',
                'malawi': 'malawi',
                'bénin': 'benin',
                'shqipëria': 'albania',
                'republic-of-macedonia': 'north macedonia',
                'северна македония': 'north macedonia',
                'албания': 'albania',
                'белгија': 'belgium',
                'democratic-republic-of-the-congo': 'democratic republic of the congo',
                'ghana': 'ghana',
                'europese unie': 'europe',
                'volksrepubliek china': 'china',
                'united-arab-emirates': 'united arab emirates',
                'arménia': 'armenia',
                'norvegia': 'norway',
                'nový zéland': 'new zealand',
                'portugali': 'portugal',
                'albânia': 'albania',
                'ierland': 'ireland',
                'poľsko': 'poland',
                'nyderlandai': 'netherlands',
                'central african republic': 'central african republic',
                'algieria': 'algeria',
                'bośnia i hercegowina': 'bosnia and herzegovina',
                'chorwacja': 'croatia',
                'rosja': 'russia',
                'benin': 'benin',
                'spanish': 'spain', 
                'fr': 'france', 
                "people's republic of china": 'china', 
                'es': 'spain',
                'america': "united states",
                'ca': 'canada', 
                'be': 'belgium', 
                'iraqi kurdistan': 'irak', 
                'turks and caicos islands': 'turkey',
                'indian subcontinent': 'india', 
                'san marino': 'italy', 
                'sicily': 'italy',
                'all countries': 'world',
                'vatican city': 'italy',
                'sudáfrica': 'south africa',
                'áfrica do sul': 'south africa',
                'benín': 'benin',
                'belçika': 'belgium',
                'i̇sviçre': 'switzerland',
                'кот д\'ивоар': 'ivory coast',
                'кувейт': 'kuwait',
                'люксембург': 'luxembourg',
                'paquistão': 'pakistan',
                'gibraltar': 'united kingdom',
                'iraque': 'iraq',
                'nemčija': 'germany',
                'grčija': 'greece',
                'luksemburg': 'luxembourg',
                'španija': 'spain',
                'monténégro': 'montenegro',
                'kenya': 'kenya',
                'portugalia': 'portugal',
                'azerbaïdjan': 'azerbaijan',
                'malte': 'malta',
                'kroatia': 'croatia',
                'sveits': 'switzerland',
                'guinea': 'united states',
                'հայաստան': 'armenia',
                'estonsko': 'estonia',
                'kuwejt': 'kuwait',
                'bulgaaria': 'bulgaria',
                'rumeenia': 'romania',
                'словенија': 'slovenia',
                'thajsko': 'thailand',
                'สาธารณรัฐเช็ก': 'czech republic',
                'ประเทศสโลวาเกีย': 'slovakia',
                'мађарска': 'hungary',
                'namibia': 'namibia',
                'niger': 'niger',
                'namibie': 'namibia',
                'sudafrica': 'south africa',
                'botswana': 'botswana',
                'tanzania': 'tanzania',
                'algerie': 'algeria',
                'republic of the congo': 'republic of the congo',
                'république centrafricaine': 'central african republic',
                'guinée équatoriale': 'united states',
                'wybrzeże kości słoniowej': 'ivory coast',
                'costa d\'avorio': 'ivory coast',
                'tunezja': 'tunisia',
                'tunesië': 'tunisia',
                'brunei': 'brunei',
                'مصر': 'egypt',
                'ایالات متحده آمریکا': 'united states',
                'soomaaliya': 'somalia',
                'katar': 'qatar',
                'سوريا': 'syria',
                'اليمن': 'yemen',
                'yemen': 'yemen',
                'venäjä': 'russia',
                'finsko': 'finland',
                'viro': 'estonia',
                'salvador': 'el salvador',
                '英国': 'united kingdom',
                'turquía': 'turkey',
                'bosnia y herzegovina': 'bosnia and herzegovina',
                'bósnia e herzegovina': 'bosnia and herzegovina',
                'turquia': 'turkey',
                'irlanti': 'ireland',
                'ruoŧŧa': 'sweden',
                'sri-lanka': 'sri lanka',
                'se': 'sweden',
                'an fhraing': 'france',
                'a\' ghearmailt': 'germany',
                'poblachd na h-èireann': 'ireland',
                'an rìoghachd aonaichte': 'united kingdom',
                'dominican-republic': 'dominican republic',
                'messico': 'mexico',
                'indien': 'india',
                'benelux': 'benelux',
                'new-zealand': 'new zealand',
                'فرانس': 'france',
                'جمہوریہ آئرستان': 'ireland',
                'پاکستان': 'pakistan',
                'ریاستہائے متحدہ آمریکا': 'united states',
                'република македонија': 'north macedonia',
                'la-reunion': 'reunion',
                'portugalsko': 'portugal',
                'kolumbien': 'colombia',
                'mauritania': 'mauritania',
                'isle of man': 'united kingdom',
                'haití': 'haiti',
                'cile': 'chile',
                'équateur': 'ecuador',
                'brasilien': 'brazil',
                'br': 'brazil',
                'írán': 'iran',
                'צרפת': 'france',
                'איטליה': 'italy',
                'principato di monaco': 'monaco',
                'repubblica ceca': 'czech republic',
                'letónia': 'latvia',
                'guadalupa': 'reunion',
                'cipro': 'cyprus',
                'macedonia del norte': 'north macedonia',
                'finska': 'finland',
                'algerije': 'algeria',
                'spanyolország': 'hungary',
                'dánmárku': 'denmark',
                'βέλγιο': 'belgium',
                'guiana francesa': 'french guiana',
                'polinésia francesa': 'french polynesia',
                'jordânia': 'jordan',
                'north korea': 'north korea',
                'ประเทศจีน': 'china',
                'islândia': 'iceland',
                'zuid-afrika': 'south africa',
                'letonia': 'latvia',
                'república democrática del congo': 'democratic republic of the congo',
                'santoña': 'spain',
                'cantabria': 'spain',
                'france spain': 'france',
                'costa do marfim': 'ivory coast',
                'túnez': 'tunisia',
                'португалия': 'portugal',
                'tunesien': 'tunisia',
                'угорщина': 'hungary',
                'італія': 'italy',
                'іспанія': 'spain',
                'марокко': 'morocco',
                'mónaco': 'monaco',
                'jordania': 'jordan',
                'cabo verde': 'cape verde',
                'franca': 'france',
                'ισπανία': 'spain',
                'arábia saudita': 'saudi arabia',
                'andora': 'andorra',
                'maldives': 'maldives',
                'tunisko': 'tunisia',
                'martinik': 'martinique',
                'bosnia-and-herzegovina': 'bosnia and herzegovina',
                'швајцарска': 'switzerland',
                'bosnie-herzégovine': 'bosnia and herzegovina',
                'кипар': 'cyprus',
                'türkei': 'turkey',
                'تركيا': 'turkey',
                'amerika birleşik devletleri': 'united states',
                'řecko': 'greece',
                'royaume uni': 'united kingdom',
                'cz': 'czech republic',
                'singapura': 'singapore',
                'frankriika': 'france',
                'nuova zelanda': 'new zealand',
                'kroatië': 'croatia',
                'elfenbeinküste': 'ivory coast',
                'philippinen': 'philippines',
                'palestinian territories': 'palestine',
                'índia': 'india',
                'nova caledónia': 'australia',
                'moldavsko': 'moldova',
                'slovinsko': 'slovenia',
                '프랑스': 'france',
                '독일': 'germany',
                'filipini': 'philippines',
                'južna koreja': 'south korea',
                'zuid-korea': 'south korea',
                'corea del sud': 'south korea',
                '캐나다': 'canada',
                '네덜란드': 'netherlands',
                'tšekki': 'czech republic',
                'cambogia': 'cambodia',
                'saudi-arabia': 'saudi arabia',
                'laos': 'laos',
                'соединённые штаты америки': 'united states',
                'ประเทศกัมพูชา': 'cambodia',
                'kamerun': 'cameroon',
                'ประเทศอินโดนีเซีย': 'indonesia',
                'timor-leste': 'timor-leste',
                'wereld': 'world',
                'fiji': 'fiji',
                'ประเทศแคนาดา': 'canada',
                'ประเทศสิงคโปร์': 'singapore',
                'bangladés': 'bangladesh',
                'nepal': 'nepal',
                'pháp': 'france',
                'việt nam': 'vietnam',
                'irán': 'iran',
                'kirgisistan': 'kyrgyzstan',
                'bosnien und herzegowina': 'bosnia and herzegovina',
                'albánie': 'albania',
                'francia': 'france',
                'bosna a hercegovina': 'bosnia and herzegovina',
                'saúdská arábie': 'saudi arabia',
                'evropska unija': 'europe',
                '澳大利亚': 'australia',
                'wallis and futuna': 'wallis and futuna',
                'البحرين': 'bahrain',
                'cook islands': 'cook islands',
                'fidji': 'fiji',
                'malaisie': 'malaysia',
                'anguilla': 'anguilla',
                'montserrat': 'montserrat',
                'габон': 'gabon',
                'almanya': 'germany',
                'スイス': 'switzerland',
                'فرانسه': 'france',
                'ایران': 'iran',
                'baréin': 'bahrain',
                'fas': 'morocco',
                'népal': 'nepal',
                'ประเทศโกตดิวัวร์': 'ivory coast',
                'saint lucia': 'saint lucia',
                'regatul unit al marii britanii și al irlandei de nord': 'united kingdom',
                'somalia': 'somalia',
                'rwanda': 'rwanda',
                'sierra leone': 'sierra leone',
                'nijer': 'niger',
                'brasile': 'brazil',
                'cehia': 'czech republic',
                'slovacia': 'slovakia',
                'ue': 'europe',
                'demokratická republika kongo': 'democratic republic of the congo',
                'nova kaledonien': 'australia',
                'jugoslavija': 'yugoslavia',
                'canadà': 'canada',
                'turcia': 'turkey',
                'polynésie francaise': 'french polynesia',
                'бельгія': 'belgium',
                'francjia': 'france',
                'antigua and barbuda': 'antigua and barbuda',
                'trinidad y tobago': 'trinidad and tobago',
                'republic of ireland': 'ireland',
                'frantsa': 'france',
                'γουαδελούπη': 'reunion',
                'كوت ديفوار': 'ivory coast',
                'cina': 'china',
                'statele unite ale americii': 'united states',
                'hu': 'hungary',
                'словения': 'slovenia',
                'nieuw-caledonië': 'australia',
                'algéria': 'algeria',
                'marokkó': 'morocco',
                'république de macédoine': 'north macedonia',
                'macao': 'macau',
                'греция': 'greece',
                'lesotho': 'lesotho',
                'libanon': 'lebanon',
                'palästinensische autonomiegebiete': 'palestine',
                'vereinigte arabische emirate': 'united arab emirates',
                'dz': 'algeria',
                'pf': 'french polynesia',
                'bg': 'bulgaria',
                'mo': 'macau',
                'sa': 'saudi arabia',
                'gn': 'united states',
                've': 'venezuela',
                'pe': 'peru',
                'th': 'thailand',
                'cl': 'chile',
                'nz': 'new zealand',
                'in': 'india',
                'au': 'australia',
                'id': 'indonesia',
                'gr': 'greece',
                'co': 'colombia',
                'ro': 'romania',
                'hk': 'hong kong',
                'rs': 'serbia',
                'dk': 'denmark',
                'ae': 'united arab emirates',
                'sc': 'seychelles',
                'middle east': 'middle east',
                'kasachstan': 'kazakhstan',
                'tn': 'tunisia',
                'ci': 'ivory coast',
                'kw': 'kuwait',
                'pt': 'portugal',
                'ar': 'argentina',
                'tw': 'taiwan',
                'ga': 'gabon',
                'tg': 'togo',
                'bh': 'bahrain',
                'pk': 'pakistan',
                'pa': 'panama',
                'etats-unis': 'united states',
                'mu': 'mauritius',
                'faroe islands': 'denmark',
                'ht': 'haiti',
                'ドイツ': 'germany',
                'za': 'south africa',
                'fi': 'finland',
                'litvánia': 'lithuania',
                'ua': 'ukraine',
                'il': 'israel',
                'si': 'slovenia',
                'sk': 'slovakia',
                'south-africa': 'south africa',
                'east-germany': 'germany',
                'tr': 'turkey',
                'pl': 'poland',
                'mk': 'north macedonia',
                'île maurice': 'mauritius',
                'pr': 'puerto rico',
                'ne': 'niger',
                'cr': 'costa rica',
                'my': 'malaysia',
                'bj': 'benin',
                'ec': 'ecuador',
                'mt': 'malta',
                'vn': 'vietnam',
                'ba': 'bosnia and herzegovina',
                'qa': 'qatar',
                'by': 'belarus',
                'gd': 'grenada',
                'mx': 'mexico',
                'eg': 'egypt',
                'eu': 'europe',
                'cm': 'cameroon',
                'ng': 'nigeria',
                'ml': 'mali',
                'om': 'oman',
                'gt': 'guatemala',
                'grenada': 'grenada',
                'thaimaa': 'thailand',
                'lt': 'lithuania',
                'mr': 'mauritania',
                'papua new guinea': 'united states',
                'białoruś': 'belarus',
                'ph': 'philippines',
                'itàlia': 'italy',
                'u.s.a': 'united states',
                'sv': 'el salvador',
                'kz': 'kazakhstan',
                'lv': 'latvia',
                'cg': 'congo',
                'arabia saudyjska': 'saudi arabia',
                'turcja': 'turkey',
                'saint martin': 'france',
                'bf': 'burkina faso',
                'bd': 'bangladesh',
                'gh': 'ghana',
                'mz': 'mozambique',
                'al': 'albania',
                'uz': 'uzbekistan',
                'pm': 'saint pierre and miquelon',
                'gy': 'guyana',
                'dj': 'djibouti',
                'uy': 'uruguay',
                'cd': 'democratic republic of the congo',
                'sowjetunion': 'soviet union',
                'frantzia': 'france',
                'espainia': 'spain',
                'mg': 'madagascar',
                'ke': 'kenya',
                'uae': 'united arab emirates',
                'td': 'chad',
                'méxico españa': 'mexico spain',
                'az': 'azerbaijan',
                'norveška': 'norway',
                'republik kongo': 'republic of the congo',
                'np': 'nepal',
                'gi': 'gibraltar',
                'ad': 'andorra',
                'yugoslavia': 'serbia',
                'porto rico': 'puerto rico',
                'czechia': 'czech republic',
                'kr': 'south korea',
                'md': 'moldova',
                'ประเทศนิวซีแลนด์': 'new zealand',
                'абхазия': 'abkhazia',
                'zimbabwe': 'zimbabwe',
                'mc': 'monaco',
                'република ирландия': 'republic of ireland',
                'lr': 'liberia',
                'yt': 'mayotte',
                'cy': 'cyprus',
                'nowa kaledonia': 'australia',
                'je': 'jersey',
                'gg': 'guernsey',
                'hashemite kingdom of jordan': 'jordan',
                'lëtzebuerg (land)': 'luxembourg',
                'santona': 'saint',
                'هولندا': 'netherlands',
                'congo': 'congo',
                'ivory coast': 'cote d\'ivoire',
                'norsko': 'norway',
                'lc': 'saint lucia',
                'macedonia': 'north macedonia',
                'emirados árabes unidos': 'united arab emirates',
                'tajlandia': 'thailand',
                'me': 'montenegro',
                'america': 'united states',
                'wf': 'wallis and futuna',
                'do': 'dominican republic',
                'united-states-of-america': 'united states',
                'indonesië': 'indonesia',
                'maleisië': 'malaysia',
                'filipijnen': 'philippines',
                'republika chińska': 'china',
                'ge': 'georgia',
                'croazia': 'croatia',
                'uniunea europeană': 'europe',
                'evropská unie': 'europe',
                'cape verde': 'cape verde',
                'szlovénia': 'slovenia',
                '++': 'unknown',
                'kolumbia': 'colombia',
                'タイ王国': 'thailand',
                'grekland': 'greece',
                'polinesia perancis': 'french polynesia',
                'libano': 'lebanon',
                'usbekistan': 'uzbekistan',
                'tadschikistan': 'tajikistan',
                'weißrussland': 'belarus',
                'republic-of-the-congo': 'republic of the congo',
                'ky': 'cayman islands',
                'republic of lithuania': 'lithuania',
                'توغو': 'togo',
                'is': 'iceland',
                'bhutan': 'bhutan',
                'paraguai': 'paraguay',
                'uruguai': 'uruguay',
                'it:..': 'italy',
                'am': 'armenia',
                '荷蘭': 'netherlands',
                'japāna': 'japan',
                'japonija': 'japan',
                'ir': 'iran',
                'izrael': 'israel',
                'py': 'paraguay',
                'cu': 'cuba',
                'yu': 'serbia',
                'ประเทศตุรกี': 'turkey',
                'netherlands france': 'france',
                'ägypten': 'egypt',
                'lk': 'sri lanka',
                'турция': 'turkey',
                'palestine': 'palestine',
                'wyspy owcze': 'faroe islands',
                'остров рождества': 'christmas island',
                'hr': 'croatia',
                'état unis': 'united states',
                'jo': 'jordan',
                'iq': 'iraq',
                'ni': 'nicaragua',
                'パキスタン': 'pakistan',
                '中国': 'china',
                'american samoa': 'american samoa',
                'mm': 'myanmar',
                'cv': 'cape verde',
                'словакия': 'slovakia',
                'km': 'comoros',
                'syrie': 'syria',
                'kambodscha': 'cambodia',
                'la': 'laos',
                'bn': 'brunei',
                'south america': 'south america',
                'turkije': 'turkey',
                'surinam': 'suriname',
                'ukrajina': 'ukraine',
                'vu': 'vanuatu',
                'filipinas': 'philippines',
                'm': 'unknown',
                'cypr': 'cyprus',
                'république démocratique allemande': 'german democratic republic',
                'tunis': 'tunisia',
                'естония': 'estonia',
                'storbritannia': 'united kingdom',
                'tz': 'tanzania',
                'cw': 'curaçao',
                'bosnia': 'bosnia and herzegovina',
                'thailandia': 'thailand',
                'fo': 'faroe islands',
                'lenkija': 'poland',
                'ee': 'estonia',
                'costa-rica': 'costa rica',
                'republic of moldova': 'moldova',
                'na': 'namibia',
                'объединённые арабские эмираты': 'united arab emirates',
                'unione europea': 'europe',
                'beļģija': 'belgium',
                'caribisch nederland': 'caribbean netherlands',
                'south-korea': 'south korea',
                'el-salvador': 'el salvador',
                'spánia': 'spain',
                'الكاميرون': 'cameroon',
                'santa lucía': 'saint lucia',
                'romanya': 'romania',
                'i̇spanya': 'spain',
                'reino-unido': 'united kingdom',
                'curazao': 'curaçao',
                'узбекистан': 'uzbekistan',
                'guayana francesa': 'french guiana',
                'mv': 'maldives',
                'bosznia-hercegovina': 'bosnia and herzegovina',
                'észtország': 'estonia',
                'jm': 'jamaica',
                'et': 'ethiopia',
                'ao': 'angola',
                'sint maarten': 'sint maarten',
                'bulgarija': 'bulgaria',
                'chad': 'chad',
                'cezayir': 'algeria',
                'suopma': 'finland',
                'iraqi kurdistan': 'iraq',
                '---': 'unknown',
                'egipto': 'egypt',
                'caribbean netherlands': 'caribbean netherlands',
                'fr €': 'france',
                'zambia': 'zambia',
                'bs': 'bahamas',
                'cf': 'central african republic',
                'uganda': 'uganda',
                'sr': 'suriname',
                'gq': 'united states',
                'guinea ecuatorial': 'united states',
                'bb': 'barbados',
                '西班牙': 'spain',
                'san martín': 'saint martin',
                'san vicente y las granadinas': 'saint vincent and the grenadines',
                'sx': 'sint maarten',
                'argentyna': 'argentina',
                'ukraina': 'ukraine',
                'san marino': 'san marino',
                'arabia saudită': 'saudi arabia',
                'polinesia francese': 'french polynesia',
                'ประเทศเม็กซิโก': 'mexico',
                'pobřeží slonoviny': 'ivory coast',
                'spojené arabské emiráty': 'united arab emirates',
                'gabun': 'gabon',
                'österrike': 'austria',
                'argentina - español': 'argentina',
                'armenia - pyсский': 'armenia',
                'aruba - español': 'aruba',
                'asia pacific': 'asia',
                'australia - english': 'australia',
                'austria - deutsch': 'austria',
                'azerbaijan - русский': 'azerbaijan',
                'belarus - pyсский': 'belarus',
                'belgium - français': 'belgium',
                'belgium - nederlands': 'belgium',
                'bolivia - español': 'bolivia',
                'bosnia i hercegovina - bosnian': 'bosnia and herzegovina',
                'botswana - english': 'botswana',
                'brazil - português': 'brazil',
                'bulgaria - български': 'bulgaria',
                'cambodia - english': 'cambodia',
                'cambodia - ភាសាខ្មែរ': 'cambodia',
                'canada - english': 'canada',
                'canada - français': 'canada',
                'chile - español': 'chile',
                'china - 中文': 'china',
                'colombia - español': 'colombia',
                'costa rica - español': 'costa rica',
                'croatia - hrvatski': 'croatia',
                'cyprus - ελληνικά': 'cyprus',
                'czech republic - čeština': 'czech republic',
                'denmark - dansk': 'denmark',
                'ecuador - español': 'ecuador',
                'el salvador - español': 'el salvador',
                'estonia - eesti': 'estonia',
                'europe': 'europe',
                'finland - suomi': 'finland',
                'france - français': 'france',
                'georgia - ქართული': 'georgia',
                'germany - deutsch': 'germany',
                'ghana - english': 'ghana',
                'greece - ελληνικά': 'greece',
                'guatemala - español': 'guatemala',
                'honduras - español': 'honduras',
                'hong kong - 粵語': 'hong kong',
                'hungary - magyar': 'hungary',
                'iceland - íslenska': 'iceland',
                'india - english': 'india',
                'indonesia - bahasa indonesia': 'indonesia',
                'ireland - english': 'ireland',
                'israel - עברית': 'israel',
                'italy - italiano': 'italy',
                'jamaica - english': 'jamaica',
                'japan - 日本語': 'japan',
                'kazakhstan - pyсский': 'kazakhstan',
                'korea - 한국어': 'south korea',
                'kyrgyzstan - русский': 'kyrgyzstan',
                'latvia - latviešu': 'latvia',
                'lebanon - english': 'lebanon',
                'lesotho - english': 'lesotho',
                'lithuania - lietuvių': 'lithuania',
                'macau - 中文': 'macau',
                'malaysia - bahasa melayu': 'malaysia',
                'malaysia - english': 'malaysia',
                'malaysia - 中文': 'malaysia',
                'mexico - español': 'mexico',
                'middle east & africa': 'middle east and africa',
                'moldova - român': 'moldova',
                'mongolia - монгол хэл': 'mongolia',
                'namibia - english': 'namibia',
                'netherlands - nederlands': 'netherlands',
                'new zealand - english': 'new zealand',
                'nicaragua - español': 'nicaragua',
                'north macedonia - македонски јазик': 'north macedonia',
                'norway - norsk': 'norway',
                'panamá - español': 'panama',
                'paraguay - español': 'paraguay',
                'perú - español': 'peru',
                'philippines - english': 'philippines',
                'poland - polski': 'poland',
                'portugal - português': 'portugal',
                'puerto rico - español': 'puerto rico',
                'república dominicana - español': 'dominican republic',
                'romania - română': 'romania',
                'russia - русский': 'russia',
                'serbia - srpski': 'serbia',
                'singapore - english': 'singapore',
                'slovak republic - slovenčina': 'slovakia',
                'slovenia - slovene': 'slovenia',
                'south africa -english': 'south africa',
                'spain - español': 'spain',
                'swaziland - english': 'eswatini',
                'sweden - svenska': 'sweden',
                'switzerland - deutsch': 'switzerland',
                'switzerland - français': 'switzerland',
                'taiwan - 中文': 'taiwan',
                'thailand - ไทย': 'thailand',
                'trinidad & tobago - english': 'trinidad and tobago',
                'turkey - türkçe': 'turkey',
                'ukraine - yкраї́нська': 'ukraine',
                'united kingdom - english': 'united kingdom',
                'united states - english': 'united states',
                'united states - español': 'united states',
                'uruguay - español': 'uruguay',
                'venezuela - español': 'venezuela',
                'vietnam - tiếng việt': 'vietnam',
                'zambia - english': 'zambia',
                'mongolei': 'mongolia',
                'xk': 'kosovo',
                'zentralafrikanische republik': 'central african republic',
                'latinoamerica': 'latin america',
                'bermuda': 'bermuda',
                'zm': 'zambia',
                'pakistán': 'pakistan',
                '5018 rue harwood': 'canada',
                'allemagne nazi': 'germany',
                'шпанија': 'spain',
                'london': 'united kingdom',
                'slovenië': 'slovenia',
                'bhoutan': 'bhutan',
                'madagascar - toamasina': 'madagascar',
                'madžarska': 'hungary',
                'maurícia': 'mauritius',
                'tailândia': 'thailand',
                'ly': 'libya',
                'ベルギー': 'belgium',
                'camerún': 'cameroon',
                'gambia': 'gambia',
                'united states minor outlying islands': 'united states',
                'írország': 'ireland',
                'литва': 'lithuania',
                'itävalta': 'austria',
                'malasia': 'malaysia',
                'birmanie': 'myanmar',
                'camerun': 'cameroon',
                'liberia': 'liberia',
                'السنغال': 'senegal',
                'bahamas': 'bahamas',
                'américa': 'america',
                'belleville wa': 'united states',
                'kazachstan': 'kazakhstan',
                'ps': 'palestine',
                'tt': 'trinidad and tobago',
                'ethiopia': 'ethiopia',
                'الاتحاد الأوروبي': 'europe',
                'ryssland': 'russia',
                'îles cook': 'cook islands',
                'fj': 'fiji',
                'カナダ': 'canada',
                'уједињено краљевство': 'united kingdom',
                'サウジアラビア': 'saudi arabia',
                'černá hora': 'montenegro',
                'coreia do sul': 'south korea',
                'chorvátsko': 'croatia',
                'malezja': 'malaysia',
                'либия': 'libya',
                'liettua': 'lithuania',
                'oroszország': 'hungary',
                'lux': 'luxembourg',
                'hn': 'honduras',
                'libia': 'libya',
                'brazylia': 'brazil',
                'korean tasavalta': 'south korea',
                'northern mariana islands': 'united states',
                'puerto-rico': 'united states',
                'ahvenanmaan maakunta': 'aland islands',
                'moldávia': 'moldova',
                'state of palestine': 'palestine',
                'unknown': 'unknown',
                'イタリア': 'italy',
                'azərbaycan': 'azerbaijan',
                'virgin-islands-of-the-united-states': 'united states',
                'čekija': 'czech republic',
                'suedia': 'sweden',
                'guam': 'united states',
                'bq': 'bonaire',
                'france.': 'france',
                'bm': 'bermuda',
                'sudan': 'sudan',
                'yémen': 'yemen',
                'north-macedonia': 'north macedonia',
                'belize': 'belize',
                'モロッコ': 'morocco',
                'egito': 'egypt',
                'السودان': 'sudan',
                'u.s.a.': 'united states',
                'pw': 'palau',
                'sambia': 'zambia',
                'ameriketako estatu batuak': 'united states',
                'soudan': 'sudan',
                'airija': 'ireland',
                '.': 'unknown',
                'bw': 'botswana',
                'equatorial guinea': 'united states',
                'кипър': 'cyprus',
                'camboya': 'cambodia',
                'ss': 'south sudan',
                'gu': 'guam',
                'ai': 'anguilla',
                'meksiko': 'mexico',
                'saint vincent and the grenadines': 'saint vincent and the grenadines',
                'китайская народная республика': 'china',
                'オーストラリア': 'australia',
                'γερμανία': 'germany',
                'stato di palestina': 'palestine',
                'prepared for siwin foods edmonton alberta t6b 3v2': 'canada',
                'sierra-leone': 'sierra leone',
                'maldive': 'maldives',
                'pg': 'united states',
                'united states of america': 'united states',
                'monako': 'monaco',
                'finlanda': 'finland',
                'česká republika': 'czech republic',
                'mn': 'mongolia',
                'ευρωπαϊκή ένωση': 'europe',
                'greenland': 'denmark',
                'er': 'eritrea',
                'обединени арабски емирства': 'united arab emirates',
                'ルクセンブルク': 'luxembourg',
                'アイルランド': 'ireland',
                'ニュージーランド': 'new zealand',
                'severní makedonie': 'north macedonia',
                'ليتوانيا': 'lithuania',
                'cipar': 'cyprus',
                'sm': 'san marino',
                'tunézia': 'tunisia',
                'repubblica dominicana': 'dominican republic',
                'colômbia': 'colombia',
                'aw': 'aruba',
                'sao tomé and príncipe': 'sao tome and principe',
                'যুক্তরাজ্য': 'united kingdom',
                'comoros': 'comoros',
                'germa': 'germany',
                'moldawien': 'moldova',
                'малта': 'malta',
                'hellas': 'greece',
                'ug': 'uganda',
                'ニューカレドニア': 'australia',
                'aland-islands': 'aland islands',
                'vi': 'united states virgin islands',
                'rw': 'rwanda',
                'sardinia': 'italy',
                'японія': 'japan',
                'mannin': 'isle of man',
                'reeriaght unnaneysit': 'united kingdom',
                'republica mexicana': 'mexico',
                'republika południowej afryki': 'south africa',
                'georgien': 'georgia',
                '南アフリカ共和国': 'south africa',
                'espagnol': 'spanish',
                'ye': 'yemen',
                'vatican city': 'vatican city',
                'indonesien': 'indonesia',
                'kn': 'saint kitts and nevis',
                'bo': 'bolivia',
                'en: españa': 'spain',
                'северна македонија': 'north macedonia',
                'албанија': 'albania',
                'sy': 'syria',
                'im': 'isle of man',
                'beyaz rusya': 'belarus',
                'nowa zelandia': 'new zealand',
                'المجر': 'hungary',
                'norga': 'norway',
                'tjeckien': 'czech republic',
                'eeuu': 'united states',
                'birmania': 'myanmar',
                'македонија': 'north macedonia',
                'sd': 'sudan',
                'ливан': 'lebanon',
                'tasty foods αβγε': 'greece',
                'камерун': 'cameroon',
                'монгол улс': 'mongolia',
                'mp': 'northern mariana islands',
                'so': 'somalia',
                'русия': 'russia',
                '::': 'unknown',
                'イラク': 'iraq',
                'macedonia de nord': 'north macedonia',
                'líbia': 'libya',
                'japani': 'japan',
                'vg': 'british virgin islands',
                'ag': 'antigua and barbuda',
                '中華人民共和国': 'people\'s republic of china',
                'turkiye': 'turkey',
                'ประเทศญี่ปุ่น': 'japan',
                'indian subcontinent': 'indian subcontinent',
                'エルサルバドル': 'el salvador',
                'emirati arabi uniti': 'united arab emirates',
                'saint-marin': 'san marino',
                'british virgin islands': 'british virgin islands',
                'tjekkiet': 'czech republic',
                '意大利': 'italy',
                'tonga': 'tonga',
                'obala bjelokosti': 'ivory coast',
                'wietnam': 'vietnam',
                'jamaïque': 'jamaica',
                'turks and caicos islands': 'turks and caicos islands',
                'moçambique': 'mozambique',
                'cc': 'cocos (keeling) islands',
                'filipiny': 'philippines',
                'kurdistan irakien': 'iraqi kurdistan',
                'va': 'vatican city',
                'servië': 'serbia',
                '沙特阿拉伯': 'saudi arabia',
                'zw': 'zimbabwe',
                'mondo': 'world',
                'macedonia del nord': 'north macedonia',
                'sl': 'sierra leone',
                'moldavië': 'moldova',
                'нидерланды': 'netherlands',
                'kp': 'north korea',
                'iirimaa': 'ireland',
                'egitto': 'egypt',
                'islanti': 'iceland',
                'na stàitean aonaichte': 'united states',
                'bz': 'belize',
                'belice': 'belize',
                'bi': 'burundi',
                'bellingham wa usa': 'united states',
                'as': 'american samoa',
                'الاردن': 'jordan',
                'dm': 'dominica',
                'ken': 'kenya',
                'アラブ首長国連邦': 'united arab emirates',
                'nyl': 'unknown',
                'samoa': 'samoa',
                'wit-rusland': 'belarus',
                'txekia': 'czech republic',
                'luxenburgo': 'luxembourg',
                'индия': 'india',
                'brazil france': 'france',
                'dél-korea': 'south korea',
                'bermudas': 'bermuda',
                'īrija': 'ireland',
                'coquitlam bc': 'canada',
                'salwador': 'el salvador',
                'amerika syarikat': 'united states',
                'جميع البلدان': 'all countries',
                'киргизия': 'kyrgyzstan',
                'kuba': 'cuba',
                'bih': 'bosnia and herzegovina',
                'аржентина': 'argentina',
                'молдова': 'moldova',
                'indie': 'india',
                'omán': 'oman',
                'sudán del sur': 'south sudan',
                'украйна': 'ukraine',
                'дания': 'denmark',
                'جنوب أفريقيا': 'south africa',
                'japonsko': 'japan',
                'армения': 'armenia',
                'gm': 'gambia',
                'fiyi': 'fiji',
                'st': 'são tomé and príncipe',
                'slov': 'unknown',
                'šveice': 'switzerland',
                'デンマーク': 'denmark',
                'albanië': 'albania',
                'tc': 'turks and caicos islands',
                'الهند': 'india',
                'maldivas': 'maldives',
                'შვეიცარია': 'switzerland',
                'ශ් රී ලංකාව': 'sri lanka',
                'roemenie': 'romania',
                'russian federation': 'russia',
                'jordánsko': 'jordan',
                'ভুটান': 'bhutan',
                'ভারত': 'india',
                'নেপাল': 'nepal',
                'মার্কিন যুক্তরাষ্ট্র': 'united states',
                'mw': 'malawi',
                'y deyrnas unedig': 'united kingdom',
                'ck': 'cook islands',
                'монголия': 'mongolia',
                'territorios palestinos': 'palestine',
                'giappone': 'japan',
                'ประเทศซาอุดีอาระเบีย': 'saudi arabia',
                'éthiopie': 'ethiopia',
                'эстония': 'estonia',
                'польша': 'poland',
                'kıbrıs cumhuriyeti': 'cyprus',
                'vc': 'saint vincent and the grenadines',
                'ireland & uk': 'united kingdom',
                'yhdistyneet arabiemiirikunnat': 'united arab emirates',
                'chint': 'unknown',
                'малайзия': 'malaysia',
                'egipt': 'egypt',
                'malásia': 'malaysia',
                'u.s. minor outlying islands': 'united states',
                'leedu': 'lithuania',
                'gruusia': 'georgia',
                'république serbe de bosnie': 'serbia',
                'япония': 'japan',
                'romani': 'romania',
                'afganistán': 'afghanistan',
                'the-bahamas': 'bahamas',
                'filippinene': 'philippines',
                'ôsterreich': 'austria',
                'spojené kráľovstvo': 'united kingdom',
                'west africa': 'west africa',
                'الأراضي الفلسطينية': 'palestine',
                'νότια αφρική': 'south africa',
                'tanzanie': 'tanzania',
                'ประเทศมาเลเซีย': 'malaysia',
                'jordanië': 'jordan',
                'vatican': 'vatican city',
                'sb': 'solomon islands',
                'sz': 'eswatini',
                'armenië': 'armenia',
                'territori palestinesi': 'palestine',
                'ประเทศฟิลิปปินส์': 'philippines',
                'bg::bulgaria': 'bulgaria',
                'läti': 'latvia',
                'letland': 'latvia',
                'велика британія': 'ukraine',
                'тунис': 'tunisia',
                'bosnië en herzegovina': 'bosnia and herzegovina',
                'central america': 'central america',
                'france 🇫🇷': 'france',
                'urugwaj': 'uruguay',
                'cocoa horizons': 'unknown',
                'arab saudi': 'saudi arabia',
                'british-indian-ocean-territory': 'british indian ocean territory',
                'ruanda': 'rwanda',
                'färöer': 'faroe islands',
                'ijsland': 'iceland',
                'færøerne': 'faroe islands',
                'belanda': 'netherlands',
                'korea selatan': 'south korea',
                'nouvelle caledonie': 'australia',
                'northern ireland': 'united kingdom',
                'wales': 'united kingdom',
                'antigua-and-barbuda': 'antigua and barbuda',
                'ouganda': 'uganda',
                'kroatija': 'croatia',
                'etiopía': 'ethiopia',
                'saint-kitts-and-nevis': 'saint kitts and nevis',
                'nouvelle-aquitaine': 'france',
                'virazeil': 'france',
                'quebec': 'canada',
                'the netherlands': 'netherlands',
                'japonia': 'japan',
                'word': 'unknown',
                'aus': 'australia',
                'беларусь': 'belarus',
                'made in the u k (ni)': 'united kingdom',
                'wa usa': 'united states',
                'baden': 'germany',
                'ouzbékistan': 'uzbekistan',
                'dr congo': 'democratic republic of the congo',
                'ariège': 'france',
                'imported by mccormick canada': 'canada',
                'on canada n6a 4z2': 'canada',
                'vancouver canada': 'canada',
                'vancouver bc canada': 'canada',
                'product of usa. packed in canada. imported by: strong international trading inc. richmond bc | www.siti.ca': 'canada',
                'rakúsko': 'austria',
                'norwa': 'norway',
                '马来西亚': 'malaysia',
                'natural calm canada 5 idleswift dr. thornhill on l4j 1k6': 'canada',
                'マダガスカル': 'madagascar',
                'santo domingo': 'dominican republic',
                'hoa kỳ': 'united states',
                'svalbard et jan mayen': 'norway',
                'europa': 'europe',
                'corsica': 'france',
                'الدمام': 'damam',
                'dubai': 'united arab emirates',
                'asia': 'asia',
                'brasill': 'brazil',
                'sicile': 'sicily',
                'surrey bc canada': 'canada',
                'italien': 'italy',
                'germany': 'germany',
                'france': 'france',
                'united states': 'united states',
                'irlande': 'ireland',
                'united kingdom': 'united kingdom',
                'états-unis': 'united states',
                'canada': 'canada',
                'suisse': 'switzerland',
                'schweiz': 'switzerland',
                'spain': 'spain',
                'deutschland': 'germany',
                'slovenia': 'slovenia',
                'frankreich': 'france',
                'netherlands': 'netherlands',
                'switzerland': 'switzerland',
                'de': 'germany',
                'italy': 'italy',
                'romania': 'romania',
                'españa': 'spain',
                'australia': 'australia',
                'world': 'world',
                'guadeloupe': 'reunion',
                'república dominicana': 'dominican republic',
                'estados unidos': 'united states',
                'nederland': 'netherlands',
                'bolivia': 'bolivia',
                'méxico': 'mexico',
                'new zealand': 'new zealand',
                'sweden': 'sweden',
                'alemania': 'germany',
                'italia': 'italy',
                'antarctic': 'antarctica',
                'royaume-uni': 'united kingdom',
                'belgique': 'belgium',
                'pays-bas': 'netherlands',
                'suède': 'sweden',
                'denemark': 'denmark',
                'norvège': 'norway',
                'espagne': 'spain',
                'pologne': 'poland',
                'none': np.nan,
                'inde': 'india',
                'autriche': 'austria',
                'espagne': 'spain',
                'united-kingdom': 'united kingdom',
                'hongrie': 'hungary',
                'république tchèque': 'czech republic',
                'france': 'france',
                'united-states': 'united states',
                'république tchèque': 'czech republic',
                'united-kingdom': 'united kingdom',
                'thailande': 'thailand',
                'états-unis': 'united states',
                'egypte': 'egypt',
                'états-unis': 'united states',
                'territoires palestiniens': 'palestine',
                'irlande': 'ireland',
                'états-unis': 'united states',
                'japon': 'japan',
                'canada': 'canada',
                'réunion': 'france',
                'monde': 'world',
                'france': 'france',
                'croatie': 'croatia',
                'irlande': 'ireland',
                'allemagne': 'germany',
                'états-unis': 'united states',
                'suisse': 'switzerland',
                'taiwan': 'taiwan',
                'belgique': 'belgium',
                'luxembourg': 'luxembourg',
                'argentine': 'argentina',
                'maroc': 'morocco',
                'brésil': 'brazil',
                'belgique': 'belgium',
                'allemagne': 'germany',
                'france': 'france',
                'guatemala': 'guatemala',
                'australie': 'australia',
                'mexique': 'mexico',
                'arabie saoudite': 'saudi arabia',
                'arabie saoudite': 'saudi arabia',
                'émirats arabes unis': 'united arab emirates',
                'irak': 'iraq',
                'koweït': 'kuwait',
                'émirats arabes unis': 'united arab emirates',
                'roumanie': 'romania',
                'costa rica': 'costa rica',
                'moldavie': 'moldova',
                'martinique': 'france',
                'new caledonia': 'australia',
                'singapore': 'singapore',
                'sverige': 'sweden',
                'usa': 'united states',
                'polynésie française': 'french polynesia',
                'french polynesia': 'french polynesia',
                'at': 'austria',
                'suiza': 'switzerland',
                'mexique': 'mexico',
                'ch': 'switzerland',
                'panamá': 'panama',
                'nouvelle-calédonie': 'france',
                'panama': 'panama',
                'brazil': 'brazil',
                'australien': 'australia',
                'kanada': 'canada',
                'russia': 'russia',
                'vereinigtes königreich': 'united kingdom',
                'países bajos': 'netherlands',
                'norway': 'norway',
                'reino unido': 'united kingdom',
                'monde': 'world',
                'yhdysvallat': 'united states',
                'suomi': 'finland',
                'made in canada from domestic and imported ingredients.': 'canada',
                'regno unito': 'united kingdom',
                'finland': 'finland',
                'ประเทศฝรั่งเศส': 'france',
                'สหราชอาณาจักร': 'united kingdom',
                '法国': 'france',
                '香港': 'hong kong',
                'hong kong': 'hong kong',
                'maurice': 'mauritius',
                'ประเทศไทย (thai)': 'thailand',
                '中华人民共和国': 'china',
                'liban': 'lebanon',
                'philippines': 'philippines',
                'niederlande': 'netherlands',
                'belgien': 'belgium',
                'belgio': 'belgium',
                'germania': 'germany',
                'belgia': 'belgium',
                'sveitsi': 'switzerland',
                'saksa': 'germany',
                'ranska': 'france',
                'espanja': 'spain',
                'yhdistynyt kuningaskunta': 'united kingdom',
                'spagna': 'spain',
                'malaysia': 'malaysia',
                'guyana': 'guyana',
                'hungary': 'hungary',
                'mundo': 'world',
                'canadá': 'canada',
                'barbados': 'barbados',
                '中華民國': 'taiwan',
                'mexiko': 'mexico',
                'saint kitts and nevis': 'saint kitts and nevis',
                'us': 'united states',
                'haïti': 'haiti',
                'el salvador': 'el salvador',
                'china': 'china',
                'bahreïn': 'bahrain',
                'italie': 'italy',
                'serbia': 'serbia',
                'フランス': 'france',
                'colombia': 'colombia',
                'réunion': 'france',
                'lebanon': 'lebanon',
                'oman': 'oman',
                'corée du sud': 'south korea',
                'trinidad and tobago': 'trinidad and tobago',
                'sénégal': 'senegal',
                'γαλλία': 'france',
                'ελλάδα': 'greece',
                'greece': 'greece',
                'niemcy': 'germany',
                'cuba': 'cuba',
                'portugal': 'portugal',
                'kuwait': 'kuwait',
                'österreich': 'austria',
                'französisch-polynesien': 'french polynesia',
                'israël': 'israel',
                'israel': 'israel',
                'puerto rico': 'puerto rico',
                'the bahamas': 'bahamas',
                'en': 'united kingdom',
                'polen': 'poland',
                'schweden': 'sweden',
                'aruba': 'aruba',
                'polinesia francesa': 'french polynesia',
                '美国': 'united states',
                'uk': 'united kingdom',
                'angola': 'angola',
                'bolivie': 'bolivia',
                'frança': 'france',
                'maroc': 'morocco',
                'アメリカ合衆国': 'united states',
                'noruega': 'norway',
                'dominican republic': 'dominican republic',
                'wielka brytania': 'united kingdom',
                'guinée': 'united states',
                'jordan': 'jordan',
                'burkina faso': 'burkina faso',
                'it': 'italy',
                'vietnam': 'vietnam',
                'pakistan': 'pakistan',
                'العراق': 'iraq',
                'россия': 'russia',
                'франция': 'france',
                'българия': 'bulgaria',
                'algérie': 'algeria',
                'saint pierre and miquelon': 'saint pierre and miquelon',
                'كندا': 'canada',
                'saint-pierre-et-miquelon': 'saint pierre and miquelon',
                'ascension island': 'ascension island',
                'côte d\'ivoire': 'ivory coast',
                'jan mayen': 'norway',
                'uruguay': 'uruguay',
                'lb': 'lebanon',
                'haiti': 'haiti',
                '加拿大': 'canada',
                'new-caledonia': 'france',
                'gb': 'united kingdom',
                'england': 'united kingdom',
                'svizzera': 'switzerland',
                'bélgica': 'belgium',
                'russland': 'russia',
                'mauritius': 'mauritius',
                'indonésie': 'indonesia',
                'arménie': 'armenia',
                '瑞士': 'switzerland',
                'autriche': 'austria',
                'grecia': 'greece',
                'grèce': 'greece',
                'india': 'india',
                'poland': 'poland',
                'curaçao': 'curaçao',
                'perancis': 'france',
                'indonesia': 'indonesia',
                'selandia baru': 'new zealand',
                'swiss': 'switzerland',
                'finnland': 'finland',
                'polska': 'poland',
                'südkorea': 'south korea',
                'south africa': 'south africa',
                'ecuador': 'ecuador',
                'chile': 'chile',
                'perú': 'peru',
                'honduras': 'honduras',
                'nicaragua': 'nicaragua',
                'turkey': 'turkey',
                'arabie saoudite': 'saudi arabia',
                'spojené státy americké': 'united states',
                'meksyk': 'mexico',
                'émirats arabes unis': 'united arab emirates',
                'croatia': 'croatia',
                'cambodia': 'cambodia',
                'neukaledonien': 'france',
                'republik china': 'china',
                'spojené království': 'united kingdom',
                'guernsey': 'guernsey',
                'mauricio': 'mauritius',
                'singapour': 'singapore',
                'european union': 'europe',
                'jamaica': 'jamaica',
                'denmark': 'denmark',
                'luxemburg': 'luxembourg',
                'hawaii': 'united states',
                'german democratic republic': 'germany', 
                'corea del sur': 'south korea',
                'tunisie': 'tunisia',
                'soviet union': 'russia', 
                'algeria': 'algeria',
                'jordanie': 'jordan',
                'ประเทศสวิตเซอร์แลนด์': 'switzerland',
                'fr  €': 'france', 
                'hongkong': 'hong kong',
                'verenigde staten van amerika': 'united states',
                'ηνωμένο βασίλειο': 'united kingdom',
                'république démocratique du congo': 'democratic republic of the congo',
                'tunísia': 'tunisia',
                'togo': 'togo',
                'qatar': 'qatar',
                'dinamarca': 'denmark',
                'guyane': 'french guiana',
                'union européenne': 'europe',
                'bulgaria': 'bulgaria',
                'zjednoczone królestwo': 'united kingdom',
                'somalía': 'somalia',
                'unión europea': 'europe',
                'líbano': 'lebanon',
                'belgië': 'belgium',
                'peru': 'peru',
                'luxemburgo': 'luxembourg',
                'zwitserland': 'switzerland',
                'jordanien': 'jordan',
                'تونس': 'tunisia',
                'république tchèque': 'czech republic',
                'românia': 'romania',
                'saint-pierre und miquelon': 'saint pierre and miquelon',
                'égypte': 'egypt',
                'monaco': 'monaco',
                'cyprus': 'cyprus',
                'الجزائر': 'algeria',
                'vezuela': 'venezuela',
                'finlande': 'finland',
                '日本': 'japan',
                'afrique du sud': 'south africa',
                'cayman islands': 'cayman islands',
                'الإمارات العربية المتحدة': 'united arab emirates',
                'irlanda': 'ireland',
                'paraguay': 'paraguay',
                'denemarken': 'denmark',
                'italië': 'italy',
                'noorwegen': 'norway',
                'spanje': 'spain',
                'zweden': 'sweden',
                'لبنان': 'lebanon',
                'فرنسا': 'france',
                'cameroon': 'cameroon',
                'mongolia': 'mongolia',
                'irland': 'ireland',
                'myanmar': 'myanmar',
                'marruecos': 'morocco',
                'भारत': 'india',
                'senegal': 'senegal',
                'tchad': 'chad',
                'suriname': 'suriname',
                'bulgarie': 'bulgaria',
                'albania': 'albania',
                'chili': 'chile',
                'norwegen': 'norway',
                'cameroun': 'cameroon',
                'virgin islands of the united states': 'united states',
                'japón': 'japan',
                'الولايات المتحدة': 'united states',
                'bangladesh': 'bangladesh',
                'australië': 'australia',
                'nieuw-zeeland': 'new zealand',
                'slowakije': 'slovakia',
                'dominica': 'dominica',
                'méxico': 'mexico',
                'suecia': 'sweden',
                'бельгия': 'belgium',
                'nigeria': 'nigeria',
                'mađarska': 'hungary',
                'italija': 'italy',
                'poljska': 'poland',
                'japon': 'japan',
                'বাংলাদেশ': 'bangladesh',
                'włochy': 'italy',
                'hiszpania': 'spain',
                'szwajcaria': 'switzerland',
                'frankrike': 'france',
                'lotyšsko': 'latvia',
                'litva': 'lithuania',
                'polsko': 'poland',
                'djibouti': 'djibouti',
                'dänemark': 'denmark',
                'tyskland': 'germany',
                'finlândia': 'finland',
                'espanha': 'spain',
                'suécia': 'sweden',
                'lithuania': 'lithuania',
                'suíça': 'switzerland',
                'south korea': 'south korea',
                'švedska': 'sweden',
                'německo': 'germany',
                'islande': 'iceland',
                'grécia': 'greece',
                'itália': 'italy',
                'polónia': 'poland',
                'hongrie': 'hungary',
                'serbie': 'serbia',
                'союз советских социалистических республик': 'ussr',
                'brésil': 'brazil',
                'ukraine': 'ukraine',
                'ísland': 'iceland',
                'türkiye': 'turkey',
                'madagascar': 'madagascar',
                'macau': 'macau',
                'franța': 'france',
                'україна': 'ukraine',
                'latvia': 'latvia',
                'estonia': 'estonia',
                'германия': 'germany',
                'швейцария': 'switzerland',
                'duitsland': 'germany',
                'südafrika': 'south africa',
                'bulharsko': 'bulgaria',
                'czech-republic': 'czech republic',
                'nizozemsko': 'netherlands',
                'austrija': 'austria',
                'alemanha': 'germany',
                'áustria': 'austria',
                'némorszag': 'hungary',
                'kroatien': 'croatia',
                'csehország': 'czech republic',
                'lengyelország': 'poland',
                'svédország': 'sweden',
                'rumania': 'romania',
                'ungarn': 'hungary',
                'países baixos': 'netherlands',
                'австрия': 'austria',
                'финландия': 'finland',
                'швеция': 'sweden',
                'bulgarien': 'bulgaria',
                'tschechien': 'czech republic',
                'slowakei': 'slovakia',
                'slowenien': 'slovenia',
                'lituania': 'lithuania',
                'испания': 'spain',
                'república checa': 'czech republic',
                'marrocos': 'morocco',
                'полша': 'poland',
                'румъния': 'romania',
                'сърбия': 'serbia',
                'хърватия': 'croatia',
                'ungheria': 'hungary',
                'storbritannien': 'united kingdom',
                'rumänien': 'romania',
                'finlandia': 'finland',
                'polonia': 'poland',
                'италия': 'italy',
                'украина': 'ukraine',
                'белгия': 'belgium',
                'griechenland': 'greece',
                'alankomaat': 'netherlands',
                'olaszország': 'hungary',
                'románia': 'romania',
                'danmark': 'denmark',
                'amerikai egyesült államok': 'united states',
                'ruotsi': 'finland',
                'tanska': 'denmark',
                'paesi bassi': 'netherlands',
                'france switzerland germany': 'france',
                'nederländerna': 'sweden',
                'унгария': 'hungary',
                'nizozemska': 'netherlands',
                'španjolska': 'spain',
                'ujedinjeno kraljevstvo': 'united kingdom',
                'espanya': 'spain',
                'regne unit': 'united kingdom',
                'norwegia': 'norway',
                'hongarije': 'hungary',
                'češka': 'czech republic',
                'slovačka': 'slovakia',
                'lu': 'luxembourg',
                'república da irlanda': 'ireland',
                'švédsko': 'sweden',
                'rakousko': 'austria',
                'serbien': 'serbia',
                'czechy': 'czech republic',
                'litwa': 'lithuania',
                'holandia': 'netherlands',
                'słowacja': 'slovakia',
                'itálie': 'italy',
                'prancūzija': 'france',
                'vokietija': 'germany',
                'šveicarija': 'switzerland',
                'lietuva': 'lithuania',
                'slovensko': 'slovakia',
                'croácia': 'croatia',
                'sérvia': 'serbia',
                'eslováquia': 'slovakia',
                'eslovénia': 'slovenia',
                'birleşik krallık': 'united kingdom',
                'slovakia': 'slovakia',
                'republik zypern': 'cyprus',
                'bułgaria': 'bulgaria',
                'eslovenia': 'slovenia',
                'bulgária': 'bulgaria',
                'hungria': 'hungary',
                'roménia': 'romania',
                'puola': 'poland',
                'slovenija': 'slovenia',
                'srbija': 'serbia',
                'bugarska': 'bulgaria',
                'svezia': 'sweden',
                'nouvelle-zélande': 'new zealand',
                'görögország': 'greece',
                'belgicko': 'belgium',
                'francúzsko': 'france',
                'nemecko': 'germany',
                'rusko': 'russia',
                'croatie': 'croatia',
                'croacia': 'croatia',
                'hungría': 'hungary',
                'švýcarsko': 'switzerland',
                'dania': 'denmark',
                'grecja': 'greece',
                'szwecja': 'sweden',
                'albanien': 'albania',
                'estonija': 'estonia',
                'latvija': 'latvia',
                'švajčiarsko': 'switzerland',
                'oostenrijk': 'austria',
                'united kingdom & ireland': 'united kingdom',
                'eslovaquia': 'slovakia',
                'słowenia': 'slovenia',
                'francija': 'france',
                'moldova': 'moldova',
                'malta': 'malta',
                'съединени американски щати': 'united states',
                'обединено кралство великобритания и северна ирландия': 'united kingdom',
                'slovénie': 'slovenia',
                'rumunsko': 'romania',
                'tsjechië': 'czech republic',
                'slovacchia': 'slovakia',
                'slovaquie': 'slovakia',
                'łotwa': 'latvia',
                'lituânia': 'lithuania',
                'maďarsko': 'hungary',
                'španělsko': 'spain',
                'gabon': 'gabon',
                'španielsko': 'spain',
                'belgija': 'belgium',
                'grčka': 'greece',
                'србија': 'serbia',
                'ie': 'ireland',
                'frankrig': 'denmark',
                'rumunjska': 'romania',
                'portogallo': 'portugal',
                'إيطاليا': 'italy',
                'чехия': 'czech republic',
                'republika srpska': 'bosnia and herzegovina',
                'cn': 'china',
                'chine': 'china',
                'austrália': 'australia',
                'iran': 'iran',
                'algerien': 'algeria',
                'nederlân': 'netherlands',
                'pérou': 'peru',
                'švica': 'switzerland',
                'スペイン': 'spain',
                'kína': 'china',
                'ausztria': 'austria',
                'bèlgica': 'belgium',
                'belgie': 'belgium',
                'austrálie': 'australia',
                '대한민국': 'south korea',
                'french guiana': 'french guiana',
                're': 'reunion',
                'af': 'afghanistan',
                'argelia': 'algeria',
                'argentine': 'argentina',
                'colombie': 'colombia',
                'russie': 'russia',
                'mali': 'mali',
                'martinica': 'martinique',
                'reunión': 'reunion',
                'reunion': 'reunion',
                'jp': 'japan',
                'guadalupe': 'reunion',
                'cote-d-ivoire': 'ivory coast',
                'казахстан': 'kazakhstan',
                'afghanistan': 'afghanistan',
                'saint-martin': 'saint martin',
                'marocco': 'morocco',
                'biélorussie': 'belarus',
                'mq': 'martinique',
                'kazakhstan': 'kazakhstan',
                'marokko': 'morocco',
                'tunisia': 'tunisia',
                'république du congo': 'republic of the congo',
                'maroko': 'morocco',
                'mayotte': 'mayotte',
                'estonie': 'estonia',
                'french-polynesia': 'french polynesia',
                'thaïlande': 'thailand',
                'австралия': 'australia',
                'мароко': 'morocco',
                'нова зеландия': 'new zealand',
                'estónia': 'estonia',
                'andorra': 'andorra',
                'nova zelândia': 'new zealand',
                'rússia': 'russia',
                'tailandia': 'thailand',
                'ประเทศออสเตรเลีย': 'australia',
                'ประเทศออสเตรีย': 'austria',
                'ประเทศเบลเยียม': 'belgium',
                'ประเทศเยอรมนี': 'germany',
                'ประเทศอิตาลี': 'italy',
                'ประเทศเลบานอน': 'lebanon',
                'ประเทศโมร็อกโก': 'morocco',
                'ประเทศโรมาเนีย': 'romania',
                'ประเทศสเปน': 'spain',
                'åland islands': 'finland',
                'bielorussia': 'belarus',
                'frakland': 'france',
                '#value!': np.nan,
                'nl': 'netherlands',
                'koeweit': 'kuwait',
                'dom tom': 'france',
                'алжир': 'algeria',
                'reunião': 'reunion',
                'dom-tom': 'france',
                'ประเทศรัสเซีย': 'russia',
                'สหรัฐอเมริกา': 'united states',
                'sg': 'singapore',
                'svájc': 'switzerland',
                'латвия': 'latvia',
                'грузия': 'georgia',
                'nueva caledonia': 'australia',
                'ru': 'russia',
                'seychelles': 'seychelles',
                'costa de marfil': 'ivory coast',
                'sjedinjene američke države': 'united states',
                'danska': 'denmark',
                'rusija': 'russia',
                'burkina-faso': 'burkina faso',
                'norge': 'norway',
                'li': 'liechtenstein',
                'реюнион': 'reunion',
                'lussemburgo': 'luxembourg',
                'vanuatu': 'vanuatu',
                'roemenië': 'romania',
                'rumunia': 'romania',
                'ma': 'morocco',
                'viêt nam': 'vietnam',
                'albanie': 'albania',
                'argélia': 'algeria',
                'pas': np.nan,
                'kh': 'cambodia',
                'الأردن': 'jordan',
                'mf': 'saint martin',
                'french-guiana': 'french guiana',
                'mongolie': 'mongolia',
                'gp': 'reunion',
                'französisch-guayana': 'french guiana',
                'nuova caledonia': 'australia',
                'france la réunion': 'reunion',
                'сенегал': 'senegal',
                'cambodge': 'cambodia',
                'jersey': 'jersey',
                'france 🇨🇵🇫🇷': 'france',
                'gf': 'french guiana',
                'angleterre': 'england',
                'andorre': 'andorra',
                'irak': 'iraq',
                'emirats arabes unis': 'united arab emirates',
                'democratic republic of the congo': 'democratic republic of the congo',
                'bulgarije': 'bulgaria',
                'griekenland': 'greece',
                'république dominicaine': 'dominican republic',
                'spania': 'spain',
                'nc': 'australia',
                'ucrania': 'ukraine',
                'welt': 'world',
                'liechtenstein': 'liechtenstein',
                'estland': 'estonia',
                'hollande': 'netherlands',
                'turquie': 'turkey',
                'mauritanie': 'mauritania',
                'iceland': 'iceland',
                'сингапур': 'singapore',
                'szerbia': 'serbia',
                'srbsko': 'serbia',
                'georgia': 'georgia',
                'ungaria': 'hungary',
                'avstrija': 'austria',
                'hrvaška': 'croatia',
                'republika srbska': 'bosnia and herzegovina',
                'bosna in hercegovina': 'bosnia and herzegovina',
                'črna gora': 'montenegro',
                'bosna i hercegovina': 'bosnia and herzegovina',
                'sjeverna makedonija': 'north macedonia',
                'albanija': 'albania',
                'saudijska arabija': 'saudi arabia',
                'republic of macedonia': 'north macedonia',
                'bosnia and herzegovina': 'bosnia and herzegovina',
                'montenegro': 'montenegro',
                'nordmazedonien': 'north macedonia',
                'szlovákia': 'slovakia',
                'француска': 'france',
                'босна и херцеговина': 'bosnia and herzegovina',
                'crna gora': 'montenegro',
                'црна гора': 'montenegro',
                'nya kaledonien': 'australia',
                'singapur': 'singapore',
                'русија': 'russia',
                'prantsusmaa': 'france',
                'hispaania': 'spain',
                'eesti': 'estonia',
                'saksamaa': 'germany',
                'dánsko': 'denmark',
                'chińska republika ludowa': 'china',
                'нидерландия': 'netherlands',
                'estija': 'estonia',
                'suomija': 'finland',
                'rumunija': 'romania',
                'švedija': 'sweden',
                'jungtinė karalystė': 'united kingdom',
                'chipre': 'cyprus',
                'κύπρος': 'cyprus',
                'белоруссия': 'belarus',
                'bělorusko': 'belarus',
                'argentinien': 'argentina',
                'saudi-arabien': 'saudi arabia',
                'イギリス': 'united kingdom',
                'bahrain': 'bahrain',
                'deutsche demokratische republik': 'east germany',
                'немачка': 'germany',
                'німеччина': 'germany',
                'польща': 'poland',
                'węgry': 'hungary',
                'north macedonia': 'north macedonia',
                'swaziland': 'eswatini',
                'elveția': 'switzerland',
                'macédoine du nord': 'north macedonia',
                'east germany': 'germany',
                'chypre': 'cyprus',
                'بلجيكا': 'belgium',
                'ألمانيا': 'germany',
                'island': 'iceland',
                'alemanya': 'germany',
                'ليبيا': 'libya',
                'росія': 'russia',
                'unkari': 'hungary',
                'lucembursko': 'luxembourg',
                'chorvatsko': 'croatia',
                'rusland': 'russia',
                'no': 'norway',
                'danimarca': 'denmark',
                'kosovo': 'kosovo',
                'bolivien': 'bolivia',
                'deut': 'germany',
                'rusia': 'russia',
                'belarus': 'belarus',
                'kyrgyzstan': 'kyrgyzstan',
                'tajikistan': 'tajikistan',
                'uzbekistan': 'uzbekistan',
                'armenia': 'armenia',
                'азербайджан': 'azerbaijan',
                'azerbaijan': 'azerbaijan',
                'australija': 'australia',
                'lettonie': 'latvia',
                'lettland': 'latvia',
                'fransa': 'france',
                'aserbaidschan': 'azerbaijan',
                'lituanie': 'lithuania',
                'jungtinės amerikos valstijos': 'united states',
                'sri lanka': 'sri lanka',
                'เขตบริหารพิเศษฮ่องกง': 'hong kong',
                'นิวแคลิโดเนีย': 'australia',
                'neuseeland': 'new zealand',
                'таджикистан': 'tajikistan',
                'франція': 'france',
                'латвія': 'latvia',
                'ucrânia': 'ukraine',
                'ucraina': 'ukraine',
                'republica moldova': 'moldova',
                'moldavie': 'moldova',
                'géorgie': 'georgia',
                'საქართველო': 'georgia',
                'hong-kong': 'hong kong',
                'قطر': 'qatar',
                '中華民国': 'taiwan',
                '澳门': 'macau',
                'mozambique': 'mozambique',
                'arabia saudita': 'saudi arabia',
                'ישראל': 'israel',
                'irlandia': 'ireland',
                'zjednoczone emiraty arabskie': 'united arab emirates',
                'norja': 'norway',
                'المملكة المتحدة': 'united kingdom',
                'المغرب': 'morocco',
                'republic of ireland': 'ireland',
                'europäische union': 'europe',
                'franciaország': 'france', 
                'spanien': 'spain', 
                'česko': 'czech republic', 
                'francie': 'france', 
                'nagy-britannia': 'united kingdom', 
                'magyarország': 'hungary', 
                'frankrijk': 'france', 
                'verenigd koninkrijk': 'united kingdom', 
                'vereinigte staaten von amerika': 'united states', 
                'la réunion': 'reunion', 
                'svijet': 'world', 
                'francuska': 'france', 
                'hrvatska': 'croatia', 
                'irska': 'ireland', 
                'njemačka': 'europe', 
                'sjedinjene-američke-države': 'united states', 
                'švicarska': 'switzerland', 
                "stati uniti d'america": 'united states', 
                'saint kitts and nevis': 'united states', 
                'el salvador': 'salvador', 
                'emiratos árabes unidos': 'united arab emirates', 
                'francja': 'france', 
                'stany zjednoczone': 'united states', 
                'brasil': 'brazil', 
                'guernsey': 'united kingdom', 
                'french guiana': 'united states', 
                'saint pierre and miquelon': 'united states', 
                'trinidad and tobago': 'united states',
                'mŕxico': 'mexico', 
                'latvia': 'lithuania', 
                'ussr': 'russia', 
                'macau': 'china', 
                'németország': 'germany', 
                'litauen': 'lithuania', 
                'saint martin': 'reunion', 
                'guadeloupe': 'reunion', 
                'republic of the congo': 'democratic republic of the congo', 
                'mayotte': 'reunion', 
                'new caledonia': 'australia', 
                'seychelles': 'reunion', 
                'liechtenstein': 'switzerland',
                'france - la réunion': 'reunion', 
                'jersey': 'united kingdom', 
                'england': 'united kingdom', 
                'madagascar': 'reunion', 
                'east germany': 'germany', 
                'bangladesh': 'india', 
                'francia  españa': 'france', 
                'france  spain': 'france', 
                'palestinian territories': 'palestine', 
                'europäische union': 'europe', 
                'soviet union': 'russia', 
                'republic of ireland': 'ireland', 
                'middle east:': 'romania',
                'saint': 'united states', 
                'papua new guinea': 'united states',
                'канада': 'canada', 
                'south america': 'peru',
                'zimbabwe': 'reunion', 
                'america': 'united states',
                'product of usa. packed in canada.  imported by: strong international trading inc. richmond bc | www.siti.ca': 'united states', 
                'natural calm canada 5 idleswift dr.  thornhill on  l4j 1k6': 'canada', 
            }
            
            df['countries'] = df['countries'].replace("", np.nan)
            df['countries'] = df['countries'].replace("None", np.nan)
            df['countries'] = df['countries'].replace("none", np.nan)
            df['countries'] = df['countries'].apply(
               lambda x: x if isinstance(x, list) 
                else ([] if pd.isna(x) else x.split(', '))
            )
            df['countries'] = df['countries'].apply(lambda x: x if isinstance(x, list) else ([] if x is np.nan else x.split(', ')))
            df['countries'] = df['countries'].apply(lambda x: ', '.join(x) if x else np.nan)
            df['countries'] = df['countries'].str.lower()  
            df['countries'] = df['countries'].apply(clean_abrev)  
            df['countries'] = df['countries'].replace(country_mapping)
            df['countries'] = df['countries'].fillna(np.nan)  
            def process_countries(countries):
                if isinstance(countries, list):
                    # Convert non-string items to strings, filter out any NaNs
                    cleaned_countries = [str(item) for item in countries if isinstance(item, str) or not pd.isna(item)]
                    return ', '.join(cleaned_countries)
                else:
                    return ''
            df['countries'] = df['countries'].apply(process_countries)
            country_counts = df['countries'].value_counts(normalize=True)
            rare_countries = country_counts[country_counts < 0.001].index
            def replace_rare_countries(countries):
                if not isinstance(countries, str):
                    return np.nan
                countries_list = [c.strip() for c in countries.split(',')]
                updated_countries = [c if c not in rare_countries else np.nan for c in countries_list]
                return ', '.join(filter(lambda x: x is not np.nan, updated_countries))
            df['countries'] = df['countries'].apply(replace_rare_countries)


            # traitment col ECOSCORE_NOTE
            df['ecoscore_note'] = df['ecoscore_note'].replace("unknown", np.nan)
            df['ecoscore_note'] = df['ecoscore_note'].replace("", np.nan)
            # remplace toutes les valeurs < 0 par 0, et toutes celles > 100 par 100
            df['ecoscore_note'] = df['ecoscore_note'].apply(lambda x: max(0, min(x, 100)) if x < 999 else x)


            # supprime les lignes avec trop de np.nan
            df = df[~(
            (df['groups'].isna() & df['categories'].isna()) |
            (df['ecoscore_groups'].isna() & df['groups'].isna()) |
            (df['ecoscore_groups'].isna() & df['categories'].isna())
            )]


            # traitment col LABELS
            df['labels_temp'] = df['labels_temp'].replace("", np.nan)
            df['labels_temp'] = df['labels_temp'].replace("None", np.nan)
            df['labels_temp'] = df['labels_temp'].replace("none", np.nan)
            df['labels_temp'] = df['labels_temp'].apply(
                lambda x: x if isinstance(x, list) 
                else ([] if pd.isna(x) or x is None else x.split(', '))
            )
            df['labels_temp'] = df['labels_temp'].apply(lambda x: x if isinstance(x, list) else ([] if x is np.nan else x.split(', ')))
            def extract_en_labels(labels_list):
                if isinstance(labels_list, str):
                    labels_list = labels_list.split(', ')
                return [ingredient.split(':', 1)[-1] for ingredient in labels_list if ingredient.startswith('en:')]

            df['labels'] = df['labels_temp'].apply(extract_en_labels)
            df['labels'] = df['labels'].apply(lambda x: ', '.join(x) if x else np.nan)
            df.drop(columns=['labels_temp'], inplace=True)

            def count_commas_plus_one(value):
                if pd.isna(value):  
                    return 0
                return value.count(',') + 1
            df['labels_note'] = df['labels'].apply(count_commas_plus_one)
            df.drop(columns=['labels'], inplace=True)
            # ramène toutes les notes > 9 à 9
            df['labels_note'] = df['labels_note'].apply(lambda x: min(x, 9) if pd.notna(x) else x)
            return df 



        # lecture et traitement du fichier jsonl en morceaux
        estimated_chunks = count_chunks(jsonl_01, chunk_size)
        chunk_iter = 0
        add_logs(f"start time preprocessing : {get_time()}, total chunk estimated: {estimated_chunks}")
        with open(jsonl_01, 'r') as infile, open(jsonl_02, 'w') as outfile:
            for chunk in pd.read_json(infile, lines=True, chunksize=chunk_size):
                chunk_iter = chunk_iter + 1
                processed_chunk = process_chunk(chunk)
                processed_chunk.to_json(outfile, orient='records', lines=True)
                add_logs(f"saved content, time: {get_time()}, progress: {(chunk_iter * 100) / estimated_chunks}%")




    def read_in_chunks(file_path, chunk_size):
        with open(file_path, 'r', encoding='utf-8') as f:
            chunk = []
            for line in f:
                chunk.append(json.loads(line))
                if len(chunk) >= chunk_size:
                    yield chunk
                    chunk = []
            if chunk:
                yield chunk

    def shuffle_jsonl(jsonl_02, jsonl_03, chunk_size):
        temp_file = jsonl_03 + '.temp'
        with open(temp_file, 'w', encoding='utf-8') as temp_f:
            for chunk in read_in_chunks(jsonl_02, chunk_size):
                random.shuffle(chunk)
                for obj in chunk:
                    temp_f.write(json.dumps(obj) + '\n')
        with open(temp_file, 'r', encoding='utf-8') as temp_f:
            lines = temp_f.readlines()
            random.shuffle(lines)
        with open(jsonl_03, 'w', encoding='utf-8') as f:
            f.writelines(lines)
        os.remove(temp_file)


    def line_count(jsonl_03, type):
        count = 0
        with open(jsonl_03, 'r', encoding='utf-8') as file:
            for line in file:
                if (type == 0):
                    try:
                        obj = json.loads(line)
                        if 'ecoscore_note' in obj:
                            value = obj['ecoscore_note']
                            #if isinstance(value, (int, float)) and value == 999:
                            if isinstance(value, (int, float)) and np.isnan(value):
                                count += 1
                    except json.JSONDecodeError:
                        print("Erreur de décodage JSON dans la ligne suivante :")
                        print(line)
                        continue

                elif (type == 1):
                    try:
                        obj = json.loads(line)
                        if 'ecoscore_note' in obj:
                            value = obj['ecoscore_note']
                            #if isinstance(value, (int, float)) and 0 <= value <= 999:
                            if isinstance(value, (int, float)) and (math.isnan(value) or (0 <= value <= 999)):
                                count += 1
                    except json.JSONDecodeError:
                        print("Erreur de décodage JSON dans la ligne suivante :")
                        print(line)
                        continue

                elif (type == 2):
                    try:
                        obj = json.loads(line)
                        if 'ecoscore_note' in obj:
                            value = obj['ecoscore_note']
                            #if isinstance(value, (int, float)) and 0 <= value <= 100:
                            if isinstance(value, (int, float)) and not math.isnan(value):
                                count += 1
                    except json.JSONDecodeError:
                        print("Erreur de décodage JSON dans la ligne suivante :")
                        print(line)
                        continue
        return count

    def line_repartitor(jsonl_03, train, test, valid, train_nb_line_ko, train_nb_line_ok, test_nb_line_ko, test_nb_line_ok, valid_nb_line_ko, valid_nb_line_ok):
        with jsonlines.open(train, mode='w') as train_writer, \
            jsonlines.open(test, mode='w') as test_writer, \
            jsonlines.open(valid, mode='w') as valid_writer:
            
            train_ok_iter, train_ko_iter = 0, 0
            test_ok_iter, test_ko_iter = 0, 0
            valid_ok_iter, valid_ko_iter = 0, 0
            total_iter, ok_iter, ko_iter = 0, 0, 0
            
            with jsonlines.open(jsonl_03, mode='r') as reader:
                for obj in reader:
                    ecoscore_note = obj.get('ecoscore_note', float('inf'))
                    total_iter+=1

                    if (ecoscore_note is np.nan):
                        if (valid_ko_iter < valid_nb_line_ko):
                            valid_writer.write(obj)
                            valid_ko_iter+=1
                        elif (test_ko_iter < test_nb_line_ko):
                            test_writer.write(obj)
                            test_ko_iter+=1
                        elif (train_ko_iter < train_nb_line_ko):
                            train_writer.write(obj)
                            train_ko_iter+=1    
                        ko_iter+=1

                    elif(ecoscore_note is not np.nan):                    
                        if (valid_ok_iter < valid_nb_line_ok):
                            valid_writer.write(obj)
                            valid_ok_iter+=1
                        elif (test_ok_iter < test_nb_line_ok):
                            test_writer.write(obj)
                            test_ok_iter+=1
                        elif (train_ok_iter < train_nb_line_ok):
                            train_writer.write(obj)
                            train_ok_iter+=1    
                        ok_iter+=1

            add_logs(f"nombre objets comptés: {total_iter}")
            add_logs(f"ecoscore ok comptés: {ok_iter}")
            add_logs(f"ecoscore ko comptés: {ko_iter}")
            add_logs(f"lignes ko ajoutés à valid: {valid_ko_iter}")
            add_logs(f"lignes ko ajoutés à test: {test_ko_iter}")
            add_logs(f"lignes ko ajoutés à train: {train_ko_iter}")
            add_logs(f"lignes ok ajoutés à valid: {valid_ok_iter}")
            add_logs(f"lignes ok ajoutés à test: {test_ok_iter}")
            add_logs(f"lignes ok ajoutés à train: {train_ok_iter}")
                    
    def split_jsonl_file(jsonl_02, train, test, valid, jsonl_03, chunk_size):
        shuffle_jsonl(jsonl_02, jsonl_03, chunk_size) # mélanger toutes les lignes aléatoirement dans jsonl_02
        valid_ecoscore_count = line_count(jsonl_03, type = 2) # compter le nombre de lignes avec écoscore 
        invalid_ecoscore_count = line_count(jsonl_03, type = 0) # compter le nombre de lignes autres (sans écoscore)
        line_count_number = line_count(jsonl_03, type = 1) # compter le nombre de lignes total
        # compter le nombre de lignes pour chaque fichier 
        train_nb_line_ko = math.floor((invalid_ecoscore_count * 80) / 100) # train ecoscore ko
        train_nb_line_ok = math.floor((valid_ecoscore_count * 80) / 100) # train ecoscore ok
        test_nb_line_ko = math.floor((invalid_ecoscore_count * 20) / 100) # test ecoscore ko
        test_nb_line_ok = math.floor((valid_ecoscore_count * 15) / 100) # test ecoscore ok
        valid_nb_line_ko = math.floor((invalid_ecoscore_count * 0) / 100) # valid ecoscore ko
        valid_nb_line_ok = math.floor((valid_ecoscore_count * 5) / 100) # valid ecoscore ok 
        add_logs(f"ecoscore ok: {valid_ecoscore_count}")
        add_logs(f"ecoscore ko: {invalid_ecoscore_count}")
        add_logs(f"nombre d'objets total: {line_count_number}")
        add_logs(f"ko attendus dans train: {train_nb_line_ko}")
        add_logs(f"ok attendus dans train: {train_nb_line_ok}")
        add_logs(f"ko attendus dans test: {test_nb_line_ko}")
        add_logs(f"ok attendus dans test: {test_nb_line_ok}")
        add_logs(f"ko attendus dans valid: {valid_nb_line_ko}")
        add_logs(f"ok attendus dans valid: {valid_nb_line_ok}")
        # répartir les lignes entre les fichiers
        line_repartitor(jsonl_03, train, test, valid, train_nb_line_ko, train_nb_line_ok, test_nb_line_ko, test_nb_line_ok, valid_nb_line_ko, valid_nb_line_ok)

    add_logs("01_preprocessing logs:")
    add_logs(f"chunk_size: {chunk_size} \nfile_id: {file_id} \nproject_path: {project_path} \njsonl_00 {jsonl_00} \njsonl_01: {jsonl_01} \njsonl_02: {jsonl_02} \njsonl_sample: {jsonl_sample} \ncol_to_keep: {col_to_keep}, \nstart_date: {start_date}, \ntrain: {train}, \ntest: {test}, \nvalid: {valid}, \njsonl_03: {jsonl_03}")

    # main algo
    #jsonl_filtered_creator(jsonl_00)
    #delete_file(jsonl_00)
    #main_processing(jsonl_01, jsonl_02)
    #delete_file(jsonl_01)
    none_to_nan(jsonl_03, jsonl_04)# remplacer tous les none et None par des NaN
    split_jsonl_file(jsonl_02, train, test, valid, jsonl_04, chunk_size)
    jsonl_sample_creator(jsonl_04, jsonl_sample) # puis utiliser 03 car prétraitement ok
    #delete_file(jsonl_02)
    #delete_file(jsonl_03)

    # récupérer la date du jour 
    current_date_time = datetime.now()
    end_date = current_date_time.strftime("%d/%m/%Y %H:%M:%S.%f")[:-3]
    add_logs(f"end date: {end_date}")

    # afficher temps total execution script 
    start_date = datetime.strptime(start_date, date_format)
    end_date = datetime.strptime(end_date, date_format)
    time_difference = end_date - start_date
    time_difference_minutes = time_difference.total_seconds() / 60
    add_logs(f"execution script time: {time_difference_minutes:.2f} minutes")


if __name__ == "__main__":
    chunk_size = sys.argv[1]
    file_id = sys.argv[2]
    project_path = sys.argv[3]
    
    main(chunk_size, file_id, project_path)