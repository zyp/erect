import itertools

def plot_timeline(ctx, main_start, run_start):
    from bokeh.models import BasicTickFormatter
    from bokeh.plotting import figure, show

    colors = {
        'running': 'blue',
        'suspended': 'red',
    }

    tasks = [
        (main_start, run_start, 'load_blueprint', colors['running']),
    ]

    for task in ctx.tasks.values():
        for (start, e), (end, next_e) in itertools.pairwise(task._events):
            if e in colors:
                tasks.append((start, end, task.id.str, colors[e]))

    source = {'name': [], 'start': [], 'end': [], 'color': []}
    tasks_sorted = []
    for start, end, name, color in sorted(tasks):
        source['name'].append(name)
        source['start'].append(start - main_start)
        source['end'].append(end - main_start)
        source['color'].append(color)

        if name not in tasks_sorted:
            tasks_sorted.append(name)

    tasks_sorted.reverse()

    p = figure(
        y_range = tasks_sorted,
        toolbar_location=None,
        sizing_mode='stretch_width',
        height = 100 + 10 * len(tasks),
    )
    p.hbar(y='name', left='start', right='end', fill_color='color', height=0.4, source=source)

    p.ygrid.grid_line_color = None
    p.xaxis.axis_label = 'Time (seconds)'
    p.xaxis.formatter = BasicTickFormatter(use_scientific=False)
    p.outline_line_color = None

    show(p)
