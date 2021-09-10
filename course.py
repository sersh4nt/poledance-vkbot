import xml.etree.ElementTree as ET


class Exercise:
    def __init__(self, index: str, text, image_path):
        self.index = index
        self.text = text
        self.image_path = image_path


class Lesson:
    def __init__(self, index: str, date, text, exercises):
        self.index = index
        self.date = date
        self.text = text
        self.exercises = exercises

    def __len__(self):
        return len(self.exercises)

    def add_exercise(self, exercise, index=None):
        if not index:
            self.exercises.append(exercise)
        elif isinstance(index, int):
            self.exercises.insert(index, exercise)


class Course:
    def __init__(self, path: str):
        self.path = path
        self.tree = ET.parse(self.path)
        self.root = self.tree.getroot()
        self.lessons = []
        self.parse_file()
        self.current_lesson = -1
        self.current_exercise = -1

    def __len__(self):
        return len(self.lessons)

    def update_indices(self):
        for i, lesson in enumerate(self.lessons):
            lesson.lesson_idx = str(i)
            for j, exercise in enumerate(lesson.exercises):
                exercise.lesson_idx = str(j)
        self.dump()

    def parse_file(self):
        self.lessons.clear()
        for lesson in self.root.findall('lesson'):
            exercises = []
            for exercise in lesson.findall('exercise'):
                e_id = exercise.attrib['num']
                e_text = exercise.find('text').text
                e_image = exercise.find('image').text
                exercises.append(Exercise(e_id, e_text, e_image))
            exercises.sort(key=lambda x: x.index)
            l_id = lesson.attrib['num']
            l_date = lesson.find('date').text
            l_text = lesson.find('text').text
            self.lessons.append(Lesson(l_id, l_date, l_text, exercises))
        self.lessons.sort(key=lambda x: x.index)

    def dump(self):
        course = ET.Element('course')

        for lesson in self.lessons:
            _lesson = ET.SubElement(course, 'lesson')
            _lesson.set('num', lesson.index)
            ET.SubElement(_lesson, 'date').text = lesson.date
            ET.SubElement(_lesson, 'text').text = lesson.text
            if len(lesson.exercises):
                for exercise in lesson.exercises:
                    _exercise = ET.SubElement(_lesson, 'exercise')
                    _exercise.set('num', exercise.index)
                    ET.SubElement(_exercise, 'text').text = exercise.text
                    ET.SubElement(_exercise, 'image').text = exercise.image_path

        ET.ElementTree(course).write('resources/course.xml')
        self.parse_file()
