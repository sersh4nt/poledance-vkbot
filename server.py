import hashlib
import sqlite3
import xml.etree.ElementTree as et
from datetime import datetime

import vk_api
from vk_api.bot_longpoll import *
from vk_api.keyboard import *
from vk_api.utils import *

from config import DB_NAME, ADMIN_ID
from course import *
from string_bundle import StringBundle

tree = et.parse('resources/course.xml')
root = tree.getroot()


def check_db_connection():
    conn = None
    try:
        conn = sqlite3.connect('users.db')
    except sqlite3.Error as e:
        print(e)
    finally:
        if conn:
            conn.close()


def create_db_table():
    request = """
        CREATE TABLE IF NOT EXISTS users(
            id INTEGER NOT NULL PRIMARY KEY,
            name TEXT,
            surname TEXT,
            current_lesson INTEGER,
            current_exercise INTEGER
        );
    """
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    try:
        c.execute(request)
    except sqlite3.Error as e:
        print(e)
    finally:
        if conn:
            conn.close()


def get_db_user(uid):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute(f"SELECT * from users WHERE id={uid}")
    record = c.fetchone()
    conn.close()
    return record


def check_for_db_user(uid):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute(f"SELECT EXISTS(SELECT 1 FROM users WHERE id={uid});")
    res = c.fetchone()[0] == 0
    conn.close()
    return res


def add_db_user(uid, user):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute(f"""INSERT INTO users ('id', 'name', 'surname', current_lesson, current_exercise)
        VALUES ('{uid}', '{user['first_name']}', '{user['last_name']}', 0, 0)""")
    conn.commit()
    conn.close()


def update_db_user(uid, lesson, exercise):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute(f"""UPDATE users SET current_lesson={lesson}, current_exercise={exercise} WHERE id={uid}""")
    conn.commit()
    conn.close()


def get_all_db_users():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT * FROM users")
    res = c.fetchall()
    conn.close()
    return res


def reset_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("UPDATE users SET current_lesson=0, current_exercise=0")
    conn.close()


class Server:
    def __init__(self, token, group_id):
        self.group_id = group_id
        self.vk = vk_api.VkApi(token=token)
        self.upload = vk_api.VkUpload(self.vk)
        self.longpoll = VkBotLongPoll(self.vk, group_id)
        self.vk_api = self.vk.get_api()
        self.members = self.vk_api.groups.getMembers(group_id=self.group_id, sort='id_asc')['items']
        self.pending_acc = []
        self.course = Course('resources/course.xml')
        self.course.dump()
        self.string_bundle = StringBundle()

        self.editing_cnt = -1
        self.lesson = None
        self.exercise = None
        self.lesson_idx = -1
        self.exercise_idx = -1

        check_db_connection()
        create_db_table()

        self.start_kb = VkKeyboard()
        self.admin_kb = VkKeyboard()
        self.exercise_kb = VkKeyboard()
        self.exercise_done_kb = VkKeyboard()
        self.lesson_done_kb = VkKeyboard()
        self.await_next_lesson_kb = VkKeyboard()
        self.accept_kb = VkKeyboard()
        self.edit_course_kb = VkKeyboard()
        self.edit_lesson_kb = VkKeyboard()
        self.edit_exercise_kb = VkKeyboard()
        self.insertion_kb = VkKeyboard()
        self.init_keyboards()

        for uid in ADMIN_ID:
            self.send_message(uid, self.get_str('started_successfully'), self.admin_kb)

    def init_keyboards(self):
        self.start_kb.add_button(self.get_str('start'), VkKeyboardColor.POSITIVE)

        self.admin_kb.add_button(self.get_str('check_progress'), VkKeyboardColor.POSITIVE)
        self.admin_kb.add_line()
        self.admin_kb.add_button(self.get_str('edit_course'), VkKeyboardColor.POSITIVE)
        self.admin_kb.add_button(self.get_str('delete_course'), VkKeyboardColor.NEGATIVE)
        self.admin_kb.add_line()
        self.admin_kb.add_button(self.get_str('display_course'), VkKeyboardColor.POSITIVE)
        self.admin_kb.add_line()
        self.admin_kb.add_button(self.get_str('reset_db'), VkKeyboardColor.NEGATIVE)

        self.exercise_kb.add_button(self.get_str('done'), VkKeyboardColor.POSITIVE)

        self.exercise_done_kb.add_button(self.get_str('check_progress'), VkKeyboardColor.POSITIVE)
        self.exercise_done_kb.add_button(self.get_str('next_element'), VkKeyboardColor.POSITIVE)

        self.lesson_done_kb.add_button(self.get_str('check_progress'), VkKeyboardColor.POSITIVE)
        self.lesson_done_kb.add_button(self.get_str('finish_lesson'), VkKeyboardColor.POSITIVE)

        self.accept_kb.add_button(self.get_str('accept'), VkKeyboardColor.POSITIVE)
        self.accept_kb.add_button(self.get_str('decline'), VkKeyboardColor.NEGATIVE)

        self.await_next_lesson_kb.add_button(self.get_str('check_progress'), VkKeyboardColor.POSITIVE)
        self.await_next_lesson_kb.add_button(self.get_str('next_lesson'), VkKeyboardColor.POSITIVE)

        self.edit_course_kb.add_button(self.get_str('create_new_lesson'), VkKeyboardColor.POSITIVE)
        self.edit_course_kb.add_line()
        self.edit_course_kb.add_button(self.get_str('create_new_exercise'), VkKeyboardColor.POSITIVE)
        self.edit_course_kb.add_line()
        self.edit_course_kb.add_button(self.get_str('edit_lesson'), VkKeyboardColor.POSITIVE)
        self.edit_course_kb.add_line()
        self.edit_course_kb.add_button(self.get_str('edit_exercise'), VkKeyboardColor.POSITIVE)

        self.insertion_kb.add_button(self.get_str('append'), VkKeyboardColor.POSITIVE)
        self.insertion_kb.add_line()
        self.insertion_kb.add_button(self.get_str('insert'), VkKeyboardColor.POSITIVE)

    def main_loop(self):
        for event in self.longpoll.listen():
            if event.type == VkBotEventType.MESSAGE_NEW and event.from_user:
                text = event.object.message['text']
                uid = event.object.message['from_id']
                self.members = self.vk_api.groups.getMembers(group_id=self.group_id, sort='id_asc')['items']

                if uid in self.members:
                    if text == self.get_str('start'):
                        self.check_user(uid)
                    elif text == self.get_str('done'):
                        self.check_exercise_done(uid)
                    elif text == self.get_str('accept') and uid in ADMIN_ID:
                        self.accept_exercise_admin(uid)
                    elif text == self.get_str('decline') and uid in ADMIN_ID:
                        self.decline_exercise(uid)
                    elif text == self.get_str('check_progress'):
                        self.check_progress(uid)
                    elif text == self.get_str('next_element'):
                        self.send_exercise(uid)
                    elif text == self.get_str('next_lesson'):
                        self.send_next_lesson(uid)
                    elif text == self.get_str('finish_lesson'):
                        self.finish_lesson(uid)
                    elif text == self.get_str('edit_course') and uid in ADMIN_ID:
                        self.send_message(uid, self.get_str('change_course'), self.edit_course_kb)
                        self.editing_cnt = 0
                    elif uid in ADMIN_ID and self.editing_cnt >= 0:
                        self.handle_editing(uid, text, event)
                    elif text == self.get_str('reset_db') and uid in ADMIN_ID:
                        reset_db()
                        self.send_message(uid, self.get_str('success'), self.admin_kb)
                    elif text == self.get_str('delete_course') and uid in ADMIN_ID:
                        pass # delete course
                    elif text == self.get_str('display_course') and uid in ADMIN_ID:
                        self.show_course(uid)

    def show_course(self, uid):
        for i, l in enumerate(self.course.lessons):
            self.send_message(uid, self.get_str('show_lesson').format(i + 1, l.date, l.text), self.admin_kb)
            for j, e in enumerate(l.exercises):
                self.send_message(uid, self.get_str('show_exercise').format(j + 1, e.text), self.admin_kb)
                self.send_photo(f"resources/img/{e.image_path}.png", uid)

    def handle_editing(self, uid, text, event):
        if self.editing_cnt == 0:
            # первоначальный выбор
            if text == self.get_str('create_new_lesson'):
                self.editing_cnt = 1
                self.send_message(uid, self.get_str('where_to_insert'), self.insertion_kb)
            elif text == self.get_str('create_new_exercise'):
                self.editing_cnt = 2
                self.send_message(uid, self.get_str('enter_object_number').format(len(self.course)))
            elif text == self.get_str('edit_lesson'):
                self.editing_cnt = 3
                self.send_message(uid, self.get_str('enter_object_number').format(len(self.course)))
            elif text == self.get_str('edit_exercise'):
                self.editing_cnt = 4
                self.send_message(uid, self.get_str('enter_idx_idx'))

        elif self.editing_cnt == 1:
            # добавить урок - куда
            if text == self.get_str('append'):
                self.editing_cnt = 5
                self.send_message(uid, self.get_str('enter_lesson_info'))
            elif text in self.get_str('insert'):
                self.editing_cnt = 6
                self.send_message(uid, self.get_str('enter_object_number').format(len(self.course)))

        elif self.editing_cnt == 2:
            # ввод индекса урока - добавить упражнение
            self.lesson_idx = int(text) - 1
            self.send_message(uid, self.get_str('enter_exercise_text'))
            self.editing_cnt = 8

        elif self.editing_cnt == 3:
            # ввод индекса урока - изменить урок
            self.lesson_idx = int(text) - 1
            self.send_message(uid, f"{self.get_str('change_lesson')} {self.get_str('enter_lesson_info')}")
            self.editing_cnt = 10

        elif self.editing_cnt == 4:
            # ввод индексов урока и упражнения - изменение урока
            self.lesson_idx, self.exercise_idx = text.split(' ')
            self.send_message(uid, self.get_str('enter_exercise_text'))
            self.editing_cnt = 11

        elif self.editing_cnt == 5:
            # ввод урока - добавить в конце - конец ветви
            self.course.lessons.append(
                Lesson(str(len(self.course)), f'{text[6:10]}-{text[3:5]}-{text[:2]}', text[11:], [])
            )
            self.course.update_indices()
            self.send_message(uid, self.get_str('success'), self.admin_kb)
            self.editing_cnt = -1

        elif self.editing_cnt == 6:
            # ввод индекса урока - добавить урок после каковата
            self.lesson_idx = int(text)
            self.editing_cnt = 7
            self.send_message(uid, self.get_str('enter_lesson_info'))

        elif self.editing_cnt == 7:
            # ввод урока - добавить урок после каковата - конец ветви
            self.course.lessons.insert(
                self.lesson_idx,
                Lesson(str(self.lesson_idx), f'{text[6:10]}-{text[3:5]}-{text[:2]}', text[11:], [])
            )
            self.course.update_indices()
            self.send_message(uid, self.get_str('success'), self.admin_kb)
            self.editing_cnt = -1

        elif self.editing_cnt == 8:
            # ввод текста упражнения - добавить упражнение
            self.course.lessons[self.lesson_idx].exercises.append(
                Exercise(str(len(self.course.lessons[self.lesson_idx])), text, None)
            )
            self.send_message(uid, self.get_str('get_exercise_image'))
            self.editing_cnt = 9

        elif self.editing_cnt == 9 and text == '':
            # ввод картинки упражнения - добавить упражнение
            sizes = event.object.message['attachments'][0]['photo']['sizes']
            link = max(sizes, key=lambda x: x['height'])['url']
            image = requests.get(link).content
            filename = hashlib.md5(link.encode()).hexdigest()
            with open(f'resources/img/{filename}.png', 'wb') as f:
                f.write(image)
            self.course.lessons[self.lesson_idx].exercises[-1].image_path = filename
            self.send_message(uid, self.get_str('success'), self.admin_kb)
            self.course.update_indices()
            self.editing_cnt = -1

        elif self.editing_cnt == 10:
            # ввод информации об уроке
            self.course.lessons[self.lesson_idx].date = f'{text[6:10]}-{text[3:5]}-{text[:2]}'
            self.course.lessons[self.lesson_idx].text = text[11:]
            self.send_message(uid, self.get_str('success'), self.admin_kb)
            self.course.update_indices()
            self.editing_cnt = -1

        elif self.editing_cnt == 11:
            # ввод картинки упражнения - изменение упражнения
            self.course.lessons[self.lesson_idx].exercises[self.exercise_idx].text = text
            self.send_message(uid, self.get_str('get_exercise_image'))
            self.editing_cnt = 12

        elif self.editing_cnt == 12 and text == '':
            sizes = event.object.message['attachments'][0]['photo']['sizes']
            link = max(sizes, key=lambda x: x['height'])['url']
            image = requests.get(link).content
            filename = hashlib.md5(link.encode()).hexdigest()
            with open(f'resources/img/{filename}.png', 'wb') as f:
                f.write(image)
            self.course.lessons[self.lesson_idx].exercises[self.exercise_idx].image_path = filename
            self.send_message(uid, self.get_str('success'), self.admin_kb)
            self.course.update_indices()
            self.editing_cnt = -1

    def decline_exercise(self, uid):
        if len(self.pending_acc) > 0:
            self.send_message(self.pending_acc.pop(), self.get_str('try_more'), self.exercise_kb)
        else:
            self.send_message(uid, self.get_str('list_empty'), self.admin_kb)

    def accept_exercise_admin(self, uid):
        if len(self.pending_acc) > 0:
            self.accept_exercise_user(self.pending_acc.pop())
        else:
            self.send_message(uid, 'Список пуст!', self.admin_kb)

    def check_progress(self, uid):
        if uid in ADMIN_ID:
            self.send_message(uid, 'Успеваемость учеников:', self.admin_kb)
            for user in get_all_db_users():
                msg = self.get_str('user_progress_admin').format(user[1], user[2], user[4] + 1, user[3] + 1)
                self.send_message(uid, msg, self.admin_kb)
        else:
            record = get_db_user(uid)
            if record[3] >= len(self.course):
                msg = self.get_str('course_done')
            else:
                msg = self.get_str('user_progress_user').format(
                    record[3],
                    len(self.course),
                    record[4],
                    len(self.course.lessons[record[3]])
                )
            kb = self.exercise_done_kb
            if record[3] > 0 and record[4] == 0:
                kb = self.lesson_done_kb
            self.send_message(uid, msg, kb)

    def send_next_lesson(self, uid):
        lesson = get_db_user(uid)[3]
        next_lesson_date = self.get_lesson_date(lesson)
        if datetime.now().date() >= datetime.strptime(next_lesson_date, '%Y-%m-%d').date():
            self.send_lesson(uid)
            self.send_exercise(uid)
        else:
            self.send_message(uid, self.get_str('lesson_date_less'), self.await_next_lesson_kb)

    def finish_lesson(self, uid):
        lesson = get_db_user(uid)[3]
        msg = self.get_str('lesson_done').format(
            lesson + 1,
            len(self.course),
            self.get_lesson_date(lesson).strftime("%d.%m.%y")
        )
        self.send_message(uid, msg, self.await_next_lesson_kb)

    def accept_exercise_user(self, uid):
        record = get_db_user(uid)
        lesson, exercise = record[3], record[4]
        exercise += 1
        kb = self.exercise_done_kb
        if exercise > len(self.course.lessons[lesson]) - 1:
            lesson += 1
            exercise = 0
            kb = self.lesson_done_kb
        update_db_user(uid, lesson, exercise)
        self.send_message(uid, self.get_str('exercise_done'), kb)

    def check_exercise_done(self, uid):
        record = get_db_user(uid)
        for admin in ADMIN_ID:
            self.send_message(
                admin,
                self.get_str('accept_exercise').format(record[1], record[2], record[3] + 1, record[4] + 1),
                self.accept_kb
            )
        self.pending_acc.append(record[0])

    def check_user(self, uid):
        user = self.get_user_info(uid)
        if check_for_db_user(uid):
            add_db_user(uid, user)
            self.send_message(uid, self.get_str('sign_up_user'))
            for admin in ADMIN_ID:
                self.send_message(
                    admin,
                    self.get_str('sign_up_admin').format(user["first_name"], user["last_name"]),
                    keyboard=self.admin_kb
                )
        else:
            self.send_message(uid, self.get_str('already_on_course'))
        self.send_lesson(uid)
        self.send_exercise(uid)

    def send_lesson(self, uid):
        record = get_db_user(uid)
        lesson, exercise = record[3], record[4]
        self.send_message(uid, self.get_lesson_text(lesson), self.exercise_kb)

    def send_exercise(self, uid):
        record = get_db_user(uid)
        lesson, exercise = record[3], record[4]
        self.send_message(uid, self.get_exercise_text(lesson, exercise), self.exercise_kb)
        path = f'resources/img/{self.get_image_path(lesson, exercise)}.png'
        self.send_photo(path, uid)

    def send_message(self, user_id, message, keyboard=None):
        self.vk_api.messages.send(
            user_id=user_id,
            message=message,
            random_id=get_random_id(),
            keyboard=keyboard.get_keyboard() if keyboard else VkKeyboard().get_empty_keyboard()
        )

    def send_photo(self, path, uid):
        photo = self.upload.photo_messages(path)
        attachment = f"photo{photo[0]['owner_id']}_{photo[0]['id']}_{photo[0]['access_key']}"
        self.vk_api.messages.send(
            user_id=uid,
            random_id=get_random_id(),
            attachment=attachment
        )

    def get_lesson_date(self, lesson):
        return self.course.lessons[lesson].date

    def get_exercise_text(self, lesson, exercise):
        return self.course.lessons[lesson].exercises[exercise].text

    def get_lesson_text(self, lesson):
        return self.course.lessons[lesson].text

    def get_image_path(self, lesson, exercise):
        return self.course.lessons[lesson].exercises[exercise].image_path

    def get_user_info(self, uid):
        return self.vk_api.users.get(user_ids=uid, name_case='nom')[0]

    def get_str(self, str_id):
        return self.string_bundle.get_string(str_id).replace('\\n', '\n').replace('\\t', '\t')
