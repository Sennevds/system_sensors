from sys import stdout

class text_color:
    RESET = '\033[0m' #LIGHT GREY
    # Normal
    OK = '\033[0;32;48m' #GREEN
    WARNING = '\033[0;33;48m' #YELLOW
    FAIL = '\033[0;31;48m' #RED
    WHITE = '\033[0;37;48m' #WHITE
    DARK = '\033[0;30;48m' #DARK GREY
    # Coloured BG
    C_OK = '\033[0;37;42m' #GREEN
    C_WARNING = '\033[0;37;43m' #YELLOW
    C_FAIL = '\033[0;37;41m' #RED
    C_BLACK = '\033[0;30;47m' #BLACK
    # Bright
    B_OK = '\033[1;32;48m' #GREEN
    B_WARNING = '\033[1;33;48m' #YELLOW
    B_FAIL = '\033[1;31;48m' #RED
    B_WHITE = '\033[1;37;48m' #WHITE
    B_DARK = '\033[1;30;48m' #DARK GREY

def write_message_to_console(message = '', **kwargs):
    if message is None or message == '':
        print()
    else:    
        dressing = ''
        if 'tab' in kwargs and type(kwargs['tab']) == int:
            for x in range(kwargs['tab']):
                dressing = f'    {dressing}'
        if 'status' in kwargs and type(kwargs['status']) is not None:
            if kwargs['status'] == 'info':
                dressing = f'{dressing}{text_color.B_DARK}[{text_color.B_WHITE}i{text_color.B_DARK}]{text_color.RESET} '
            elif kwargs['status'] == 'ok':
                dressing = f'{dressing}{text_color.B_DARK}[{text_color.B_OK}✓{text_color.B_DARK}]{text_color.RESET} '
            elif kwargs['status'] == 'warning':
                dressing = f'{dressing}{text_color.B_DARK}[{text_color.B_WARNING}!{text_color.B_DARK}]{text_color.RESET} '
            elif kwargs['status'] == 'fail':
                dressing = f'{dressing}{text_color.B_DARK}[{text_color.B_FAIL}✗{text_color.B_DARK}]{text_color.RESET} '
        else:
            dressing = f'{dressing}{text_color.WHITE}'
        print(f'{dressing}{message}{text_color.RESET}')
    stdout.flush()