from flask import Flask, flash, jsonify, redirect, render_template, request, url_for

from service import ChannelBridge, CustomerService, LoginSessionManager


app = Flask(__name__)
app.secret_key = 'xianyu-customer-service-dev'

service = CustomerService()
bridge = ChannelBridge(service)
login_manager = LoginSessionManager(service, bridge)


@app.template_filter('from_json_list')
def from_json_list(value):
    if not value:
        return []
    import json

    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return [part.strip() for part in value.split(',') if part.strip()]


@app.route('/')
def index():
    return redirect(url_for('conversations'))


@app.route('/connect')
def connect():
    return render_template(
        'connect.html',
        account=service.get_account(),
        channel_status=bridge.get_status(),
    )


@app.post('/connect/start')
def start_connect():
    ok, message = bridge.start()
    flash(message, 'success' if ok else 'warning')
    return redirect(url_for('connect'))


@app.post('/api/channel/login/start')
def api_login_start():
    try:
        result = login_manager.start()
        return jsonify({'ok': True, **result})
    except Exception as exc:
        return jsonify({'ok': False, 'message': str(exc)}), 500


@app.get('/api/channel/login/status')
def api_login_status():
    session_id = request.args.get('session_id', '').strip()
    if not session_id:
        return jsonify({'ok': False, 'message': 'missing session_id'}), 400
    try:
        result = login_manager.status(session_id)
        return jsonify({'ok': True, **result})
    except Exception as exc:
        return jsonify({'ok': False, 'message': str(exc)}), 500


@app.post('/api/channel/listener/start')
def api_listener_start():
    ok, message = login_manager.start_listener()
    return jsonify({'ok': ok, 'message': message}), (200 if ok else 400)


@app.get('/api/channel/status')
def api_channel_status():
    return jsonify({
        'ok': True,
        'account': service.get_account(),
        'channel_status': bridge.get_status(),
    })


@app.route('/conversations')
def conversations():
    items = service.list_conversations()
    selected_id = request.args.get('conversation_id')
    selected = None
    messages = []
    if selected_id:
        selected = service.get_conversation(selected_id)
        if selected:
            service.mark_conversation_read(selected_id)
            selected = service.get_conversation(selected_id)
            messages = service.get_messages(selected_id)
    elif items:
        selected = items[0]
        service.mark_conversation_read(selected['conversation_id'])
        selected = service.get_conversation(selected['conversation_id'])
        messages = service.get_messages(selected['conversation_id'])

    return render_template(
        'conversations.html',
        conversations=items,
        selected=selected,
        messages=messages,
        account=service.get_account(),
        channel_status=bridge.get_status(),
    )


@app.post('/conversations/<conversation_id>/manual-reply')
def manual_reply(conversation_id):
    conversation = service.get_conversation(conversation_id)
    if not conversation:
        flash('会话不存在', 'error')
        return redirect(url_for('conversations'))

    content = request.form.get('content', '').strip()
    if not content:
        flash('回复内容不能为空', 'warning')
        return redirect(url_for('conversations', conversation_id=conversation_id))

    try:
        bridge.send_manual_reply(conversation_id, conversation['buyer_id'], content)
        flash('已发送人工回复', 'success')
    except Exception as exc:
        flash(f'发送失败: {exc}', 'error')
    return redirect(url_for('conversations', conversation_id=conversation_id))


@app.post('/conversations/<conversation_id>/mode')
def update_conversation_mode(conversation_id):
    manual_takeover = request.form.get('manual_takeover') == '1'
    service.set_conversation_mode(conversation_id, manual_takeover)
    flash('会话处理方式已更新', 'success')
    return redirect(url_for('conversations', conversation_id=conversation_id))


@app.route('/rules')
def rules():
    debug_text = request.args.get('debug_text', '').strip()
    debug_result = service.debug_match(debug_text) if debug_text else None
    return render_template(
        'rules.html',
        rules=service.list_rules(),
        faqs=service.list_faqs(),
        settings=service.get_settings(),
        debug_text=debug_text,
        debug_result=debug_result,
    )


@app.route('/rules/new')
def new_rule_or_faq():
    kind = request.args.get('kind', 'rule')
    if kind not in {'rule', 'faq'}:
        kind = 'rule'
    return render_template(
        'rule_form.html',
        kind=kind,
        item=None,
    )


@app.route('/rules/<int:rule_id>/edit')
def edit_rule(rule_id):
    item = service.get_rule(rule_id)
    if not item:
        flash('规则不存在', 'error')
        return redirect(url_for('rules'))
    return render_template(
        'rule_form.html',
        kind='rule',
        item=item,
    )


@app.route('/faqs/<int:faq_id>/edit')
def edit_faq(faq_id):
    item = service.get_faq(faq_id)
    if not item:
        flash('FAQ 不存在', 'error')
        return redirect(url_for('rules'))
    return render_template(
        'rule_form.html',
        kind='faq',
        item=item,
    )


@app.post('/rules/save')
def save_rule():
    service.save_rule(request.form)
    flash('规则已保存', 'success')
    return redirect(url_for('rules'))


@app.post('/rules/<int:rule_id>/delete')
def delete_rule(rule_id):
    service.delete_rule(rule_id)
    flash('规则已删除', 'success')
    return redirect(url_for('rules'))


@app.post('/faqs/save')
def save_faq():
    service.save_faq(request.form)
    flash('FAQ 已保存', 'success')
    return redirect(url_for('rules'))


@app.post('/faqs/<int:faq_id>/delete')
def delete_faq(faq_id):
    service.delete_faq(faq_id)
    flash('FAQ 已删除', 'success')
    return redirect(url_for('rules'))


@app.route('/settings', methods=['GET', 'POST'])
def settings():
    if request.method == 'POST':
        payload = {
            'auto_reply_enabled': '1' if request.form.get('auto_reply_enabled') else '0',
            'ai_reply_enabled': '1' if request.form.get('ai_reply_enabled') else '0',
            'default_reply_text': request.form.get('default_reply_text', '').strip(),
            'manual_fallback_text': request.form.get('manual_fallback_text', '').strip(),
            'ai_api_url': request.form.get('ai_api_url', '').strip(),
            'ai_api_key': request.form.get('ai_api_key', '').strip(),
            'ai_model': request.form.get('ai_model', '').strip(),
            'ai_system_prompt': request.form.get('ai_system_prompt', '').strip(),
        }
        service.save_settings(payload)
        flash('系统设置已保存', 'success')
        return redirect(url_for('settings'))

    return render_template(
        'settings.html',
        settings=service.get_settings(),
        account=service.get_account(),
        channel_status=bridge.get_status(),
    )


@app.route('/logs')
def logs():
    return render_template(
        'logs.html',
        logs=service.list_logs(),
        account=service.get_account(),
        channel_status=bridge.get_status(),
    )


if __name__ == '__main__':
    app.run(debug=False, use_reloader=False, port=5055)
