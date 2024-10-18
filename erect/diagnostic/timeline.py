def plot_timeline(ctx, main_start, run_start):
    from bokeh.models import BasicTickFormatter
    from bokeh.plotting import figure, show

    tasks = [
        (main_start, run_start, 'load_blueprint'),
    ]

    for task in ctx.tasks.values():
        if task._start is None or task._end is None:
            continue

        tasks.append((task._start, task._end, task.id.str))

    source = {'name': [], 'start': [], 'end': []}
    for start, end, name in reversed(sorted(tasks)):
        source['name'].append(name)
        source['start'].append(start - main_start)
        source['end'].append(end - main_start)

    p = figure(
        y_range = source['name'],
        toolbar_location=None,
        sizing_mode='stretch_width',
        height = 15 * len(tasks),
    )
    p.hbar(y='name', left='start', right='end', height=0.4, source=source)

    p.ygrid.grid_line_color = None
    p.xaxis.axis_label = 'Time (seconds)'
    p.xaxis.formatter = BasicTickFormatter(use_scientific=False)
    p.outline_line_color = None

    show(p)
