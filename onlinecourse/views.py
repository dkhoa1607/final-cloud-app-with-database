from django.shortcuts import render
from django.http import HttpResponseRedirect
# <HINT> Import any new Models here
from .models import Course, Enrollment, Choice, Submission
from django.contrib.auth.models import User
from django.shortcuts import get_object_or_404, render, redirect
from django.urls import reverse
from django.views import generic
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
import logging
# Get an instance of a logger
logger = logging.getLogger(__name__)
# Create your views here.


def registration_request(request):
    context = {}
    if request.method == 'GET':
        return render(request, 'onlinecourse/user_registration_bootstrap.html', context)
    elif request.method == 'POST':
        # Check if user exists
        username = request.POST['username']
        password = request.POST['psw']
        first_name = request.POST['firstname']
        last_name = request.POST['lastname']
        user_exist = False
        try:
            User.objects.get(username=username)
            user_exist = True
        except:
            logger.error("New user")
        if not user_exist:
            user = User.objects.create_user(username=username, first_name=first_name, last_name=last_name,
                                            password=password)
            login(request, user)
            return redirect("onlinecourse:index")
        else:
            context['message'] = "User already exists."
            return render(request, 'onlinecourse/user_registration_bootstrap.html', context)


def login_request(request):
    context = {}
    if request.method == "POST":
        username = request.POST['username']
        password = request.POST['psw']
        user = authenticate(username=username, password=password)
        if user is not None:
            login(request, user)
            return redirect('onlinecourse:index')
        else:
            context['message'] = "Invalid username or password."
            return render(request, 'onlinecourse/user_login_bootstrap.html', context)
    else:
        return render(request, 'onlinecourse/user_login_bootstrap.html', context)


def logout_request(request):
    logout(request)
    return redirect('onlinecourse:index')


def check_if_enrolled(user, course):
    is_enrolled = False
    if user.id is not None:
        # Check if user enrolled
        num_results = Enrollment.objects.filter(user=user, course=course).count()
        if num_results > 0:
            is_enrolled = True
    return is_enrolled


# CourseListView
class CourseListView(generic.ListView):
    template_name = 'onlinecourse/course_list_bootstrap.html'
    context_object_name = 'course_list'

    def get_queryset(self):
        user = self.request.user
        courses = Course.objects.order_by('-total_enrollment')[:10]
        for course in courses:
            if user.is_authenticated:
                course.is_enrolled = check_if_enrolled(user, course)
        return courses


class CourseDetailView(generic.DetailView):
    model = Course
    template_name = 'onlinecourse/course_details_bootstrap.html'


def enroll(request, course_id):
    course = get_object_or_404(Course, pk=course_id)
    user = request.user

    is_enrolled = check_if_enrolled(user, course)
    if not is_enrolled and user.is_authenticated:
        # Create an enrollment
        Enrollment.objects.create(user=user, course=course, mode='honor')
        course.total_enrollment += 1
        course.save()

    return HttpResponseRedirect(reverse(viewname='onlinecourse:course_details', args=(course.id,)))


def extract_answers(request):
    """Collect all checked choice IDs from the submitted exam form."""
    selected_ids = []
    for key, value in request.POST.items():
        if key.startswith('choice_'):
            try:
                selected_ids.append(int(value))
            except (TypeError, ValueError):
                continue
    return selected_ids


@login_required
@require_POST
def submit(request, course_id):
    """Persist an exam attempt and redirect to its evaluated result."""
    course = get_object_or_404(Course, pk=course_id)
    enrollment, _ = Enrollment.objects.get_or_create(
        user=request.user,
        course=course,
        defaults={'mode': Enrollment.HONOR},
    )
    submission = Submission.objects.create(enrollment=enrollment)
    selected_ids = extract_answers(request)
    valid_choices = Choice.objects.filter(
        id__in=selected_ids,
        question__lesson__course=course,
    )
    submission.choices.set(valid_choices)
    return redirect(
        'onlinecourse:show_exam_result',
        course_id=course.id,
        submission_id=submission.id,
    )


@login_required
def show_exam_result(request, course_id, submission_id):
    """Calculate the score and display per-question exam feedback."""
    course = get_object_or_404(Course, pk=course_id)
    submission = get_object_or_404(
        Submission,
        pk=submission_id,
        enrollment__course=course,
        enrollment__user=request.user,
    )
    selected_ids = list(submission.choices.values_list('id', flat=True))
    questions = course.lesson_set.prefetch_related('question_set__choice_set')

    earned_score = 0
    possible_score = 0
    question_results = []
    for lesson in questions:
        for question in lesson.question_set.all():
            possible_score += question.grade
            got_score = question.is_get_score(selected_ids)
            if got_score:
                earned_score += question.grade
            question_results.append({
                'question': question,
                'selected_choices': question.choice_set.filter(id__in=selected_ids),
                'got_score': got_score,
            })

    grade = round((earned_score / possible_score) * 100) if possible_score else 0
    context = {
        'course': course,
        'submission': submission,
        'grade': grade,
        'earned_score': earned_score,
        'possible_score': possible_score,
        'question_results': question_results,
    }
    return render(request, 'onlinecourse/exam_result_bootstrap.html', context)



