import json
import re
import os


def load_product_data(product_name, data_dir='/root/DATA'):
    """Load product JSON data from the DATA directory."""
    path = os.path.join(data_dir, 'products', f'{product_name}.json')
    with open(path) as f:
        return json.load(f)


def load_employee_data(data_dir='/root/DATA'):
    """Load employee metadata."""
    path = os.path.join(data_dir, 'metadata', 'employee.json')
    with open(path) as f:
        return json.load(f)


def _discover_schema(product_data):
    """Discover the schema of a product data file at runtime.
    Returns dict with discovered key roles:
      'messaging_key': key for chat/messaging data (list of message objects)
      'documents_key': key for document records
      'transcript_key': key for meeting transcript records
      'url_key': key for URL records
      'admin_user_ids': set of bot/admin user IDs discovered from data
    """
    schema = {
        'messaging_key': None,
        'documents_key': None,
        'transcript_key': None,
        'url_key': None,
        'admin_user_ids': set()
    }

    for key, val in product_data.items():
        if not isinstance(val, list) or len(val) == 0:
            continue
        sample = val[0]
        if not isinstance(sample, dict):
            continue

        sample_keys = set(sample.keys())

        # Detect messaging data: has Message/Channel structure or similar
        if 'Message' in sample_keys or 'Channel' in sample_keys:
            schema['messaging_key'] = key
        # Detect documents: has author + type/content fields
        elif 'author' in sample_keys and ('content' in sample_keys or 'type' in sample_keys):
            schema['documents_key'] = key
        # Detect transcripts: has transcript/participants fields
        elif 'transcript' in sample_keys or 'participants' in sample_keys:
            schema['transcript_key'] = key
        # Detect URLs: has link field
        elif 'link' in sample_keys:
            schema['url_key'] = key

    # Discover admin/bot user IDs from messaging data
    if schema['messaging_key']:
        for msg_obj in product_data[schema['messaging_key']]:
            user_data = _extract_user_from_msg(msg_obj)
            if user_data:
                uid = user_data.get('userId', '')
                # Bot/admin users typically have 'bot' or 'admin' in their ID
                if 'bot' in uid.lower() or 'admin' in uid.lower():
                    schema['admin_user_ids'].add(uid)

    return schema


def _extract_user_from_msg(msg_obj):
    """Extract user info from a message object, handling nested structures."""
    if 'Message' in msg_obj:
        inner = msg_obj['Message']
        if isinstance(inner, dict) and 'User' in inner:
            return inner['User']
    return None


def _get_doc_type_field(doc):
    """Discover the field name used for document type classification."""
    for candidate in ['type', 'doc_type', 'category', 'kind']:
        if candidate in doc:
            return candidate
    # Fallback: look for any string field that looks like a type label
    for k, v in doc.items():
        if isinstance(v, str) and k not in ('id', 'author', 'content', 'date') and len(v) < 100:
            return k
    return None


def _get_transcript_type_field(mt):
    """Discover the field name used for transcript/meeting type."""
    for candidate in ['type', 'doc_type', 'category', 'kind']:
        if candidate in mt:
            return candidate
    # Look for fields with short string values that could be type labels
    for k, v in mt.items():
        if isinstance(v, str) and k not in ('id', 'date', 'transcript') and len(v) < 100:
            return k
    return None


def search_slack(product_data, keywords, case_sensitive=False):
    """Search messaging data for keywords. Returns list of matching message dicts."""
    schema = _discover_schema(product_data)
    msg_key = schema['messaging_key']
    if not msg_key:
        return []

    results = []
    for msg_obj in product_data[msg_key]:
        user_data = _extract_user_from_msg(msg_obj)
        if not user_data:
            continue
        text = user_data.get('text', '')
        search_text = text if case_sensitive else text.lower()
        matched = False
        for kw in keywords:
            kw_check = kw if case_sensitive else kw.lower()
            if kw_check in search_text:
                matched = True
                break
        if matched:
            channel_info = msg_obj.get('Channel', {})
            results.append({
                'userId': user_data.get('userId', ''),
                'timestamp': user_data.get('timestamp', ''),
                'text': text,
                'thread_replies': msg_obj.get('ThreadReplies', []),
                'channel': channel_info.get('name', '') if isinstance(channel_info, dict) else ''
            })
    return results


def find_document_authors_and_reviewers(product_data, doc_type):
    """Find authors and reviewers for a specific document type.
    Searches document metadata, messaging conversation context, and transcripts.
    Returns dict with 'authors' and 'reviewers' keys (lists of employee IDs)."""
    authors = set()
    reviewers = set()
    schema = _discover_schema(product_data)

    # Collect document IDs and authors for this doc type
    doc_ids = set()
    doc_key = schema['documents_key']
    if doc_key:
        for doc in product_data[doc_key]:
            type_field = _get_doc_type_field(doc)
            if type_field and doc.get(type_field) == doc_type:
                authors.add(doc['author'])
                doc_ids.add(doc.get('id', ''))

    admin_ids = schema['admin_user_ids']

    # Search messaging data for review conversations
    msg_key = schema['messaging_key']
    if msg_key:
        # Group messages by channel, sorted by timestamp
        channel_messages = {}
        for msg_obj in product_data[msg_key]:
            channel_info = msg_obj.get('Channel', {})
            channel = channel_info.get('name', '') if isinstance(channel_info, dict) else ''
            user_data = _extract_user_from_msg(msg_obj)
            if not user_data:
                continue
            uid = user_data.get('userId', '')
            text = user_data.get('text', '')
            ts = user_data.get('timestamp', '')
            if channel not in channel_messages:
                channel_messages[channel] = []
            channel_messages[channel].append({
                'userId': uid, 'text': text, 'timestamp': ts
            })

        for channel, msgs in channel_messages.items():
            msgs.sort(key=lambda x: x['timestamp'])

            i = 0
            while i < len(msgs):
                m = msgs[i]
                uid = m['userId']

                # Detect a document share event: author posts message
                # containing a document link (one of the doc_ids)
                is_share = False
                if uid in authors:
                    for did in doc_ids:
                        if did in m['text']:
                            is_share = True
                            break

                if is_share:
                    share_date = m['timestamp'][:10]
                    j = i + 1
                    while j < len(msgs):
                        fm = msgs[j]
                        fm_date = fm['timestamp'][:10]
                        fm_uid = fm['userId']

                        # Stop if we move to a different day
                        if fm_date != share_date:
                            break

                        # Stop if another doc share by author
                        if fm_uid in authors:
                            is_another_share = any(did in fm['text'] for did in doc_ids)
                            if is_another_share:
                                break

                        if fm_uid in admin_ids:
                            j += 1
                            continue

                        if fm_uid not in authors:
                            fm_lower = fm['text'].lower()
                            feedback_indicators = [
                                'suggest', 'think', 'agree', 'noticed', 'could',
                                'should', 'benefit', 'helpful', 'section',
                                'include', 'add', 'expand', 'elaborate',
                                'detail', 'point', 'clarif', 'looking forward'
                            ]
                            if any(ind in fm_lower for ind in feedback_indicators):
                                reviewers.add(fm_uid)

                        j += 1
                i += 1

    # Find reviewers from transcripts
    transcript_key = schema['transcript_key']
    if transcript_key:
        for mt in product_data[transcript_key]:
            type_field = _get_transcript_type_field(mt)
            transcript_text = mt.get('transcript', '')

            is_review = False
            if type_field and mt.get(type_field) == doc_type:
                is_review = True
            elif any(did in transcript_text for did in doc_ids):
                is_review = True

            if is_review:
                participants = mt.get('participants', [])
                for pid in participants:
                    if pid not in authors:
                        reviewers.add(pid)

    return {'authors': sorted(authors), 'reviewers': sorted(reviewers)}


def find_competitor_insights(product_data):
    """Find team members who provided insights on competitor product
    strengths and weaknesses."""
    insight_providers = set()
    schema = _discover_schema(product_data)
    competitor_names = _extract_competitor_names(product_data, schema)
    admin_ids = schema['admin_user_ids']

    msg_key = schema['messaging_key']
    if not msg_key:
        return []

    for msg_obj in product_data[msg_key]:
        user_data = _extract_user_from_msg(msg_obj)
        if not user_data:
            continue
        text = user_data.get('text', '')
        uid = user_data.get('userId', '')
        text_lower = text.lower()

        if uid in admin_ids:
            continue

        # Pattern 1: Introducing a competitor product discussion
        if 'was reading about' in text_lower:
            if any(w in text_lower for w in [
                'competitor', 'gaining traction', 'interesting features',
                'strengths', 'weaknesses', 'useful to discuss'
            ]):
                insight_providers.add(uid)

        # Pattern 2: Discussing specific strengths/weaknesses of a named competitor
        # Exclude messages about 'our strengths' (referring to own product)
        if 'strength' in text_lower or 'weakness' in text_lower:
            # Skip if talking about own product strengths/weaknesses
            if 'our strength' in text_lower or 'our weakness' in text_lower:
                pass
            else:
                for comp in competitor_names:
                    if comp.lower() in text_lower:
                        insight_providers.add(uid)
                        break

    return sorted(insight_providers)


def _extract_competitor_names(product_data, schema=None):
    """Extract competitor product names from messaging discussions."""
    if schema is None:
        schema = _discover_schema(product_data)
    competitor_names = set()
    msg_key = schema['messaging_key']
    if not msg_key:
        return competitor_names

    for msg_obj in product_data[msg_key]:
        user_data = _extract_user_from_msg(msg_obj)
        if not user_data:
            continue
        text = user_data.get('text', '')
        text_lower = text.lower()
        if 'was reading about' in text_lower:
            match = re.search(r'about\s+([A-Z][a-zA-Z]+)', text)
            if match:
                name = match.group(1)
                if len(name) > 3 and name not in [
                    'This', 'That', 'These', 'Those', 'Some', 'What'
                ]:
                    competitor_names.add(name)
    return competitor_names


def find_competitor_demo_urls(product_data):
    """Find demo URLs shared for competitor products.
    Filters out internal product demo URLs."""
    demo_urls = []
    seen = set()
    schema = _discover_schema(product_data)

    # Check messaging data
    msg_key = schema['messaging_key']
    if msg_key:
        for msg_obj in product_data[msg_key]:
            user_data = _extract_user_from_msg(msg_obj)
            if not user_data:
                continue
            text = user_data.get('text', '')
            if 'demo' in text.lower() and 'http' in text:
                urls = re.findall(r'https?://[^\s]+', text)
                for url in urls:
                    if 'demo' in url.lower() and 'sf-internal' not in url:
                        clean_url = url.rstrip('.,;:!?)')
                        if clean_url not in seen:
                            seen.add(clean_url)
                            demo_urls.append(clean_url)

    # Check URL records
    url_key = schema['url_key']
    if url_key:
        for url_obj in product_data[url_key]:
            link = url_obj.get('link', '')
            if 'demo' in link.lower() and 'sf-internal' not in link:
                if link not in seen:
                    seen.add(link)
                    demo_urls.append(link)

    return sorted(demo_urls)


def create_answer(answers_dict, output_path='/root/answer.json'):
    """Create answer file with proper format."""
    result = {}
    for qid, answer in answers_dict.items():
        result[qid] = {
            'answer': answer if isinstance(answer, list) else [answer],
            'tokens': 0
        }
    with open(output_path, 'w') as f:
        json.dump(result, f, indent=4)
    return result


def run_end_to_end(question_path='/root/question.txt',
                   data_dir='/root/DATA',
                   output_path='/root/answer.json'):
    """End-to-end entry point: reads questions, discovers relevant products,
    searches enterprise data, and writes answer file."""
    with open(question_path) as f:
        questions_text = f.read()

    answers = {}
    questions = _parse_questions(questions_text)

    for qid, question in questions.items():
        q_lower = question.lower()
        product_name = _detect_product(q_lower, data_dir)
        if not product_name:
            answers[qid] = []
            continue

        data = load_product_data(product_name, data_dir)

        if 'author' in q_lower and 'reviewer' in q_lower:
            doc_type = _detect_doc_type(q_lower, data)
            result = find_document_authors_and_reviewers(data, doc_type)
            answers[qid] = result['authors'] + result['reviewers']
        elif 'demo' in q_lower and 'url' in q_lower:
            answers[qid] = find_competitor_demo_urls(data)
        elif 'competitor' in q_lower and \
             ('strength' in q_lower or 'weakness' in q_lower or 'insight' in q_lower):
            answers[qid] = find_competitor_insights(data)
        elif 'author' in q_lower:
            doc_type = _detect_doc_type(q_lower, data)
            result = find_document_authors_and_reviewers(data, doc_type)
            answers[qid] = result['authors']
        elif 'reviewer' in q_lower:
            doc_type = _detect_doc_type(q_lower, data)
            result = find_document_authors_and_reviewers(data, doc_type)
            answers[qid] = result['reviewers']
        else:
            answers[qid] = []

    result = create_answer(answers, output_path)
    return result


def _parse_questions(text):
    """Parse questions from question file format."""
    questions = {}
    lines = text.strip().split('\n')
    for line in lines:
        line = line.strip().rstrip(',')
        match = re.match(r'"(q\d+)"\s*:\s*(.+)', line)
        if match:
            qid = match.group(1)
            q_text = match.group(2).strip().rstrip(',').rstrip('?').strip()
            if q_text.startswith('"') and q_text.endswith('"'):
                q_text = q_text[1:-1]
            questions[qid] = q_text
    return questions


def _detect_product(question_lower, data_dir='/root/DATA'):
    """Detect which product the question is about."""
    products_dir = os.path.join(data_dir, 'products')
    if not os.path.exists(products_dir):
        return None
    for fname in os.listdir(products_dir):
        if fname.endswith('.json'):
            product_name = fname[:-5]
            if product_name.lower() in question_lower:
                return product_name
    return None


def _detect_doc_type(question_lower, product_data):
    """Detect which document type the question refers to."""
    schema = _discover_schema(product_data)
    doc_key = schema['documents_key']
    if not doc_key:
        return None

    doc_types = set()
    for doc in product_data[doc_key]:
        type_field = _get_doc_type_field(doc)
        if type_field:
            dt = doc.get(type_field, '')
            if dt:
                doc_types.add(dt)

    for dt in doc_types:
        if dt.lower() in question_lower:
            return dt

    best_match = None
    best_score = 0
    for dt in doc_types:
        words = dt.lower().split()
        score = sum(1 for w in words if w in question_lower)
        if score > best_score:
            best_score = score
            best_match = dt
    return best_match


def validate_answer(output_path='/root/answer.json'):
    """Validate the answer file."""
    errors = []
    if not os.path.exists(output_path):
        return ['answer file does not exist']
    with open(output_path) as f:
        data = json.load(f)
    if not isinstance(data, dict):
        errors.append('Top level must be a dict')
        return errors
    for qid, entry in data.items():
        if not isinstance(entry, dict):
            errors.append(f'{qid}: entry must be a dict')
            continue
        if 'answer' not in entry:
            errors.append(f'{qid}: missing answer field')
        else:
            ans = entry['answer']
            if not isinstance(ans, list):
                errors.append(f'{qid}: answer must be a list')
            elif len(ans) == 0:
                errors.append(f'{qid}: answer list is empty')
        if 'tokens' not in entry:
            errors.append(f'{qid}: missing tokens field')
        else:
            tok = entry['tokens']
            if not isinstance(tok, (int, float)):
                errors.append(f'{qid}: tokens must be numeric')
    if not errors:
        print('Validation passed!')
    else:
        for e in errors:
            print(f'ERROR: {e}')
    return errors
