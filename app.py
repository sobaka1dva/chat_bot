from flask import Flask, render_template, request, jsonify, session
import pandas as pd
import numpy as np
from sentence_transformers import SentenceTransformer, util
import mysql.connector 
import warnings
import re
from langdetect import detect
import string
warnings.filterwarnings(action='ignore', category=FutureWarning)


app = Flask(__name__)

# Загрузка предварительно обученной модели SBERT
model = SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')


# Загрузка эмбеддингов из файла
question_embeddings = np.load('./additions/question_embeddings.npy')

#Читаем вопросы чат-бота из файла для последующего их сравнения с пользовательским
def read_questions_from_excel(file_path):
    df = pd.read_excel(file_path)
    return df

# Считывание вопросов из Excel-файла
file_path = './additions/questions.xlsx'
df = read_questions_from_excel(file_path)

#Вспомогатьельная функция - ищет в тексте ответа ссылки и преобразует их в html
def make_links_clickable(text):
    # Шаблон для поиска URL в тексте
    url_regex = r'(https?://\S+)'
    # Замена найденных URL на HTML-ссылки
    return re.sub(url_regex, r'<a href="\1">\1</a>', text)

# Функция для отправки сообщения - сделаем ссылки кликабельными
def send_message_with_clickable_links(message):
    # Преобразуем текст сообщения, чтобы ссылки стали кликабельными
    message_with_links = make_links_clickable(message)
    # Отправляем юзеру сообщение с HTML-разметкой
    return message_with_links

#Устанавливаем контакт с БД для получения ответа на вопрос
def connect_to_db(id_qst):
    cnx = mysql.connector.connect(user='sql8707481', password='hWgYM6aJ3z', host='sql8.freesqldatabase.com', database='sql8707481')
    cursor = cnx.cursor()
    #Для корректного отображения emoji
    cursor.execute('SET NAMES utf8mb4;')
    #если в качесвте параметра получили список номеров похожих вопросов - вернем их текстом
    if type(id_qst) == list:
        s=""
        for i in range(len(id_qst)):
            request = f"SELECT * FROM questions WHERE id = {id_qst[i][1]};"
            cursor.execute(request)
            data = cursor.fetchall()
            question = data[0][1]
            if i != len(id_qst)-1:
                s+=f"❓«{question}»;"+"\n"
            else:
                s+=f"❓«{question}»."
        cursor.close()
        cnx.close()
        return s
    #если получили номер вопроса - вернем ответ на него
    else:
        request = f"SELECT * FROM questions WHERE id = {id_qst};"
        cursor.execute(request)
        data = cursor.fetchall()
        question = data[0][1]
        request = f"SELECT * FROM answers WHERE id = {id_qst};"
        cursor.execute(request)
        data = cursor.fetchall()
        #если в сообщении есть ссылка - она станет кликабельной
        answer = send_message_with_clickable_links(data[0][1])
        cursor.close()
        cnx.close()
        return f"💡Вы имели ввиду: {question}\n\n{answer}"
    
#Поиск похожего вопроса среди вопросов чат-бота
def find_most_similar_question(input_question, coincidence = 0.7):
    s=[]
    # Получение векторного представления для введенного вопроса
    input_embedding = model.encode(input_question, convert_to_tensor=True)

    # Вычисление косинусного сходства между введенным вопросом и вопросами из таблицы
    similarities = util.pytorch_cos_sim(input_embedding, question_embeddings)

    # Нахождение индекса наиболее похожего вопроса
    most_similar_index = similarities.argmax().item()

    #Если такого нет - понижаем степень схожести и ищем близкие по значению и формулировке и кладем в список
    if similarities[0][most_similar_index] <= coincidence:
        for index, row in df.iterrows():
            # Считываем эмбендинги для вопросов из эксель файла
            question_embedding = question_embeddings[index]
            ratio = util.pytorch_cos_sim(input_embedding, question_embedding)
            if(ratio >= 0.5):
                pair = (ratio, int(row['номер']))
                s.append(pair)
                s = sorted(s, key=lambda x: x[0])
                s.reverse()
        return s
    else:
        #Если нашли похожий -вернули номер, так удобнее сделать запрос к БД
        return df['номер'][most_similar_index]


#Функции проверки для языка ввода - если вводятся непонятные символы, бросаем исключениями False
def is_russian(text):
    try:
        russian_chars = re.compile('[а-яА-ЯёЁ]')
        return bool(russian_chars.search(text))
    except:
        return False

def detect_language(text):
    try:
        language = detect(text)
        return language
    except:
        return False


#Удаление знаков препинания
def remove_punctuation(input_string):
    translator = str.maketrans('', '', string.punctuation)
    return input_string.translate(translator)


# Выделение некторых аббревиатур, понижение регистра до строчных букв
def format(input_string):
    # Определяем аббревиатуры, которые нужно преобразовать в верхний регистр
    abbreviations = {'пфк', 'етис', 'пгниу', 'икнт'}
    # Разделяем строку на слова
    words = input_string.split()
    # Преобразуем каждое слово в нижний регистр, если оно не является аббревиатурой
    # Преобразуем аббревиатуры в верхний регистр, если они написаны строчными буквами
    words_transformed = [word.upper() if word.lower() in abbreviations else word.lower() for word in words]
    # Собираем обратно в строку
    return ' '.join(words_transformed)

@app.route("/")
def index():
    return render_template('chat.html')



@app.route("/get", methods=["GET", "POST"])
def chat():
    msg = request.form["msg"]
    input = msg
    #Определяем русский ли язык
    if detect_language(input) == 'ru' or is_russian(input):
        cool_question = find_most_similar_question(format(remove_punctuation(input)))
        #возвращаем ответ в зависимости от результата работы функции поиска
        return get_Chat_response(cool_question)
    else:
        return "Не смогла распознать твой стиль написания! Напиши, пожалуйста, сообщение на русском языке🙌"


def get_Chat_response(cool_question):
    # Определяем стиль для ответа
    response_style = 'style="white-space: pre-wrap; font-family: "Nunito", sans-serif; font-weight: 300; color: #FFFFFF;"'
    
    # Если вернула список - значит конкретного похожего вопроса не нашлось - есть только близкие, распечатаем их
    if type(cool_question) == list:
        if not cool_question:
            return f'<span {response_style}>😔Хм... Похоже, я не могу ответить на твой вопрос, переформулируй, пожалуйста, его.</span>'
        else:
            # Если список не пуст, значит есть близкие вопросы
            response = f'<span {response_style}>🤔Хм... Немного не поняла тебя, переформулируй, пожалуйста, свой вопрос! Возможно, ты имел ввиду это:\n</span>'
            response += f'<span {response_style}>' + connect_to_db(cool_question) + '</span>'
            return response
    else:
        # Если вернула не список, значит есть конкретный вопрос такого типа, делаем запрос к БД для поиска ответа
        return f'<span {response_style}>' + connect_to_db(cool_question) + '</span>'


if __name__ == '__main__':
    app.run()


