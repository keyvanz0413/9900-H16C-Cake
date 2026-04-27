# Resume Candidate Review Skill

## Purpose

`resume_candidate_review` finds hiring, resume, candidate, and job-application emails. When attachments are available, it extracts attachment text and builds an evidence bundle for review.

## Flow

1. Search inbox mail with hiring-related keywords.
2. Fetch attachment lists for candidate messages.
3. Run attachment extraction only when at least one candidate message has attachments.
4. Filter extracted sections by message id.
5. Return a bundle for the finalizer.

## Finalizer Expectations

For each candidate, summarize identity, target role, attachment evidence, relevant background, missing evidence, and suggested next step. Do not invent experience, skills, or role fit beyond the extracted evidence.

## Failure Mode

If attachment text is unavailable, the final answer should state that the review is based on limited metadata and should not fabricate candidate qualifications.
