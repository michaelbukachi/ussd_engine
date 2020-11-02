def add_bar_to_name(ussd_request):
    name = ussd_request.session.get('name', '')
    ussd_request.session['name'] = name + ' bar'
    return 1
