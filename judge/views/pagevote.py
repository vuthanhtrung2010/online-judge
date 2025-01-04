from django.contrib.auth.decorators import login_required
from django.db import IntegrityError
from django.db.models import F
from django.http import (
    Http404,
    HttpResponse,
    HttpResponseBadRequest,
    HttpResponseForbidden,
)
from django.utils.translation import gettext as _
from django.views.generic.base import TemplateResponseMixin
from django.views.generic.detail import SingleObjectMixin
from django.views.generic import View, ListView
from django_ratelimit.decorators import ratelimit
from django.conf import settings
from django.http import JsonResponse

from judge.models.pagevote import PageVote, PageVoteVoter, dirty_pagevote

__all__ = [
    "upvote_page",
    "downvote_page",
    "PageVoteDetailView",
    "PageVoteListView",
]


@login_required
def vote_page(request):
    try:
        delta = int(request.POST.get("delta"))
        if delta not in [1, 0, -1]:
            return HttpResponseBadRequest(
                _("Invalid value for delta. It must be 1, 0, or -1."),
                content_type="text/plain",
            )
    except ValueError:
        return HttpResponseForbidden()

    if request.method != "POST":
        return HttpResponseForbidden()

    pagevote_id = request.POST.get("id")

    if not pagevote_id:
        return HttpResponseBadRequest(
            _("Missing 'id' parameter."), content_type="text/plain"
        )

    # Ensure the user has solved at least one problem, unless they are staff
    if (
        not request.user.is_staff
        and not request.profile.submission_set.filter(
            points=F("problem__points")
        ).exists()
    ):
        return HttpResponseBadRequest(
            _("You must solve at least one problem before you can vote."),
            content_type="text/plain",
        )

    try:
        pagevote_id = int(pagevote_id)
    except ValueError:
        return HttpResponseBadRequest(
            _("Invalid ID format."), content_type="text/plain"
        )

    try:
        pagevote = PageVote.objects.get(id=pagevote_id)
    except PageVote.DoesNotExist:
        raise Http404(_("The specified PageVote does not exist."))

    vote, created = PageVoteVoter.objects.get_or_create(
        pagevote=pagevote, voter=request.profile, defaults={"score": 0}
    )

    if delta == 0:
        # Remove the vote
        if not created:
            PageVote.objects.filter(id=pagevote_id).update(
                score=F("score") - vote.score
            )
            vote.delete()
    else:
        if created:
            # New vote
            vote.score = delta
            vote.save()
            PageVote.objects.filter(id=pagevote_id).update(score=F("score") + delta)
        else:
            # Update existing vote
            PageVote.objects.filter(id=pagevote_id).update(
                score=F("score") + delta - vote.score
            )
            vote.score = delta
            vote.save()

    # Get the updated score
    current_score = PageVote.objects.get(id=pagevote_id).score

    dirty_pagevote(pagevote, request.profile)

    # Return the updated score as JSON
    return JsonResponse({"current_score": current_score})


class PageVoteDetailView(TemplateResponseMixin, SingleObjectMixin, View):
    pagevote_page = None

    def get_pagevote_page(self):
        if self.pagevote_page is None:
            raise NotImplementedError()
        return self.pagevote_page

    def get_context_data(self, **kwargs):
        context = super(PageVoteDetailView, self).get_context_data(**kwargs)
        context["pagevote"] = self.object.get_or_create_pagevote()
        return context
