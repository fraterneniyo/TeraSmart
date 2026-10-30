"""TeraSmart — standalone 10-crop farmer/planner demonstration app."""
from __future__ import annotations
import base64, hashlib, hmac, json, os, sqlite3
from datetime import date
import html
from pathlib import Path

import pandas as pd
import plotly.express as px
import requests
import streamlit as st
from core.router import IhingaRouter

ROOT = Path(__file__).resolve().parent
DB = ROOT / 'storage' / 'terasmart.sqlite3'
CROPS = {
    '101': 'Maize', '106': 'Bush bean', '110': 'Irish potato', '103': 'Sorghum',
    '107': 'Climbing bean', '108': 'Pea', '111': 'Sweet potato', '122': 'Soybean',
    '123': 'Groundnut', '305': 'Cassava'
}
DISTRICTS = json.loads((ROOT / 'data' / 'district_labels.json').read_text())['districts']
DISTRICT_NAMES = {k: v['name'] for k, v in DISTRICTS.items()}

st.set_page_config(
    page_title='TeraSmart | Plant with Insight',
    page_icon='🌾',
    layout='wide',
    initial_sidebar_state='expanded'
)
st.markdown('<style>' + (ROOT / 'assets' / 'theme.css').read_text(encoding='utf-8') + '</style>', unsafe_allow_html=True)


@st.cache_data(show_spinner=False)
def photo_data(name: str) -> str:
    p = ROOT / 'assets' / name
    return 'data:image/jpeg;base64,' + base64.b64encode(p.read_bytes()).decode() if p.exists() else ''


def hero(title: str, subtitle: str, photo: str = 'hero.jpg', eyebrow: str = 'TERASMART') -> None:
    image = photo_data(photo)
    bg = f'linear-gradient(96deg,rgba(32,39,59,.94),rgba(32,39,59,.52)),url("{image}") center/cover' if image else '#20273b'
    st.markdown(
        f'<section class="hero-card" style="background:{bg}">'
        f'<div class="tag">{eyebrow}</div><h1>{title}</h1><p>{subtitle}</p></section>',
        unsafe_allow_html=True,
    )


def heading(title: str, caption: str | None = None) -> None:
    st.markdown(
        f'<div class="section-title"><h3>{title}</h3>{f"<p>{caption}</p>" if caption else ""}</div>',
        unsafe_allow_html=True,
    )


def source_card(name: str, category: str, description: str, url: str) -> None:
    with st.container(border=True):
        st.caption(category.upper())
        st.markdown(f'#### {name}')
        st.write(description)
        st.link_button('View source', url, use_container_width=True)


def stat_tile(label: str, value: str, note: str = '') -> None:
    st.markdown(
        f'<div class="stat-tile"><span>{label}</span><strong>{value}</strong>'
        f'{f"<small>{note}</small>" if note else ""}</div>',
        unsafe_allow_html=True,
    )


def card_link(title: str, description: str, page: str, key: str) -> None:
    st.markdown(f'<div class="mini-card"><h4>{title}</h4><p>{description}</p></div>', unsafe_allow_html=True)
    if st.button(f'Open {title}', key=key, use_container_width=True):
        st.session_state.page = page
        st.rerun()


def db():
    DB.parent.mkdir(exist_ok=True)
    c = sqlite3.connect(DB, timeout=20)
    c.row_factory = sqlite3.Row
    c.execute('PRAGMA foreign_keys=ON')
    return c


def initialize() -> None:
    with db() as c:
        c.executescript('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            phone TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('farmer','planner')),
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS plots (
            id INTEGER PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id),
            name TEXT NOT NULL,
            crop TEXT NOT NULL,
            season TEXT NOT NULL,
            district TEXT NOT NULL,
            area_ha REAL NOT NULL,
            farmer_type TEXT NOT NULL DEFAULT '1',
            planted TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS forecasts (
            id INTEGER PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id),
            plot_id INTEGER NOT NULL REFERENCES plots(id),
            estimate REAL NOT NULL,
            lower REAL NOT NULL,
            upper REAL NOT NULL,
            evidence TEXT,
            recorded_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS checkins (
            id INTEGER PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id),
            plot_id INTEGER NOT NULL REFERENCES plots(id),
            stage TEXT NOT NULL,
            condition TEXT NOT NULL,
            note TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id),
            plot_id INTEGER NOT NULL REFERENCES plots(id),
            title TEXT NOT NULL,
            due TEXT,
            done INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS ledger (
            id INTEGER PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id),
            plot_id INTEGER NOT NULL REFERENCES plots(id),
            kind TEXT CHECK(kind IN ('Expense','Sale')),
            amount REAL NOT NULL,
            category TEXT,
            note TEXT,
            day TEXT NOT NULL
        );
        ''' )
        columns = {r['name'] for r in c.execute('PRAGMA table_info(plots)').fetchall()}
        for column, definition in {'seed_type': "TEXT NOT NULL DEFAULT 'Not recorded'", 'fertilizer_type': "TEXT NOT NULL DEFAULT 'Not recorded'"}.items():
            if column not in columns:
                c.execute(f'ALTER TABLE plots ADD COLUMN {column} {definition}')


def pw_hash(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode(), salt, 220000)
    return salt.hex() + ':' + digest.hex()


def check_pw(password: str, stored: str) -> bool:
    try:
        a, b = stored.split(':', 1)
        actual = hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(a), 220000)
        return hmac.compare_digest(actual, bytes.fromhex(b))
    except (ValueError, TypeError):
        return False


def query(sql: str, args=()):
    with db() as c:
        return [dict(x) for x in c.execute(sql, args).fetchall()]


def execute(sql: str, args=()):
    with db() as c:
        cur = c.execute(sql, args)
        return cur.lastrowid


def user():
    ident = st.session_state.get('user_id')
    found = query('SELECT id,name,role FROM users WHERE id=?', (ident,)) if ident else []
    return found[0] if found else None


@st.cache_resource(show_spinner='Loading crop estimation models…')
def load_router():
    return IhingaRouter(ROOT / 'data')


def router() -> IhingaRouter:
    return load_router()


def plots(owner: int):
    return query('SELECT * FROM plots WHERE user_id=? ORDER BY id DESC', (owner,))


def pick_plot(owner: int, key: str = 'pick'):
    pp = plots(owner)
    if not pp:
        st.info('Add your first plot in My Fields to continue.')
        return None
    return st.selectbox('Select plot', pp, format_func=lambda p: f"{p['name']} · {CROPS.get(p['crop'], p['crop'])}", key=key)


def gate() -> None:
    hero(
        'Plant with insight. Decide with confidence.',
        'A lighter agricultural workspace for farmers and planners, focused on field records, harvest estimation, weather and guided support.',
        'hero.jpg',
        'TERASMART / FIELD DECISION SUPPORT',
    )
    st.markdown('<div class="gate-intro">Two focused portals · Ten supported crops · Cleaner workflows</div>', unsafe_allow_html=True)
    a, b = st.tabs(['Farmer access', 'Planner access'])
    with a:
        st.markdown('### Farmer sign-in')
        st.caption('Open your account to continue managing fields, estimates and activities.')
        login_form('farmer')
        with st.expander('Create a farmer account'):
            register_form('farmer')
    with b:
        st.markdown('### Planner sign-in')
        st.caption('Planner accounts are restricted and require administrator authorization.')
        login_form('planner')
        with st.expander('Create a planner account'):
            register_form('planner')
    st.caption('Demonstration environment: records stored here may not persist on temporary cloud hosting.')


def login_form(role: str) -> None:
    with st.form('login_' + role):
        phone = st.text_input('Phone number', key='phone_' + role)
        password = st.text_input('Password', type='password', key='password_' + role)
        ok = st.form_submit_button('Sign in', type='primary', use_container_width=True)
    if ok:
        rows = query('SELECT * FROM users WHERE phone=? AND role=?', (phone.strip(), role))
        if rows and check_pw(password, rows[0]['password_hash']):
            st.session_state.user_id = rows[0]['id']
            st.session_state.page = 'Overview'
            st.rerun()
        st.error('Incorrect phone number or password for this portal.')


def register_form(role: str) -> None:
    with st.form('register_' + role):
        name = st.text_input('Full name', key='newname_' + role)
        phone = st.text_input('Phone number', key='newphone_' + role)
        password = st.text_input('Password (8 or more characters)', type='password', key='newpass_' + role)
        code = st.text_input('Administrator setup code', type='password') if role == 'planner' else None
        submitted = st.form_submit_button('Create ' + role + ' account')
    if submitted:
        if len(name.strip()) < 2 or len(phone.strip()) < 7 or len(password) < 8:
            st.error('Enter a name, valid phone number, and password of at least 8 characters.')
            return
        if role == 'planner':
            try:
                secret = str(st.secrets.get('PLANNER_SETUP_CODE', ''))
            except (FileNotFoundError, KeyError):
                secret = ''
            if len(secret) < 12 or not hmac.compare_digest(str(code or ''), secret):
                st.error('Planner account creation requires a valid administrator setup code.')
                return
        try:
            execute(
                'INSERT INTO users(name,phone,password_hash,role) VALUES(?,?,?,?)',
                (name.strip(), phone.strip(), pw_hash(password), role),
            )
            st.success('Account created. You can now sign in.')
        except sqlite3.IntegrityError:
            st.error('Phone number already registered.')


def overview(u: dict) -> None:
    if u['role'] == 'planner':
        hero(
            'Planner workspace',
            'Review registered production activity, compare districts and surface planning signals from the records available in TeraSmart.',
            'planner.jpg',
            'PLANNER / OVERVIEW',
        )
        planner_overview()
        return

    hero(
        f"Welcome back, {u['name'].split()[0]}",
        'Review your field portfolio, recent estimates and the work that still needs attention.',
        'fields.jpg',
        'FARMER / OVERVIEW',
    )
    pp = plots(u['id'])
    ff = query('SELECT * FROM forecasts WHERE user_id=? ORDER BY id DESC', (u['id'],))
    tt = query('SELECT * FROM tasks WHERE user_id=? ORDER BY due', (u['id'],))
    open_tasks = [t for t in tt if not t['done']]

    totals = query("SELECT COALESCE(SUM(CASE WHEN kind='Sale' THEN amount ELSE -amount END),0) AS balance, COALESCE(SUM(CASE WHEN kind='Sale' THEN amount ELSE 0 END),0) AS sales, COALESCE(SUM(CASE WHEN kind='Expense' THEN amount ELSE 0 END),0) AS expenses FROM ledger WHERE user_id=?", (u['id'],))[0]
    s1, s2, s3, s4, s5 = st.columns(5)
    with s1: stat_tile('Fields', str(len(pp)), 'registered plots')
    with s2: stat_tile('Area', f"{sum(p['area_ha'] for p in pp):.2f} ha", 'tracked in system')
    with s3: stat_tile('Estimates', str(len(ff)), 'saved harvest results')
    with s4: stat_tile('Pending', str(len(open_tasks)), 'unfinished activities')
    with s5: stat_tile('Farm balance', f"{totals['balance']:,.0f} RWF", 'sales minus recorded expenses')

    left, right = st.columns([1.35, 1], gap='large')
    with left:
        heading('Action board', 'Use a faster path into the next thing you want to do')
        a, b = st.columns(2)
        with a:
            card_link('My Fields', 'Register a field or review recorded plot details.', 'My Fields', 'dash_fields')
            card_link('District Weather', 'Check the district forecast before planning work.', 'District Weather', 'dash_weather')
        with b:
            card_link('Harvest Estimator', 'Calculate or revisit a model-based harvest range.', 'Harvest Estimator', 'dash_est')
            card_link('AI Assistant', 'Ask for plain-language guidance based on your records.', 'AI Assistant', 'dash_ai')

        heading('Registered fields', 'Most recent field records')
        if not pp:
            st.info('No fields yet. Open My Fields and register your first plot.')
        for p in pp[:5]:
            st.markdown(
                f'<div class="record-strip"><div><strong>{html.escape(p["name"])}</strong><span>{CROPS[p["crop"]]} · Season {p["season"]} · {DISTRICT_NAMES.get(p["district"], p["district"])} </span></div><b>{p["area_ha"]:.2f} ha</b></div>',
                unsafe_allow_html=True,
            )

    with right:
        heading('Latest estimate snapshot')
        if ff:
            latest = ff[0]
            st.markdown('<div class="focus-panel">', unsafe_allow_html=True)
            st.metric('Estimated harvest', f"{latest['estimate']:,.0f} kg")
            st.caption(f"Indicative range: {latest['lower']:,.0f}–{latest['upper']:,.0f} kg")
            st.caption('Interpret as a statistical range, not a guarantee of production.')
            st.markdown('</div>', unsafe_allow_html=True)
        else:
            st.info('No saved estimate yet. Open Harvest Estimator to generate one.')

        heading('Farm activities', '🔴 Overdue · 🟢 Upcoming / due today')
        if not open_tasks:
            st.success('No unfinished activities right now.')
        for t in sorted(open_tasks, key=lambda t: t['due'] or '9999-12-31')[:8]:
            overdue = bool(t['due'] and t['due'] < date.today().isoformat())
            marker = '🔴 Overdue' if overdue else '🟢 Upcoming' if t['due'] else '⚪ Unscheduled'
            st.markdown(f"**{marker}** — {html.escape(t['title'])}  \nDue: {t['due'] or 'Not set'}")
        if st.button('Manage all activities', key='dashboard_activities'):
            st.session_state.page = 'Farm Activities'
            st.rerun()


SEED_TYPES = ['Local', 'Improved', 'Not sure']
FERTILIZER_TYPES = ['Organic (manure/compost)', 'Inorganic (mineral/NPK)', 'None / not applied']


def field_inputs(prefix: str, existing: dict | None = None):
    """Share registration and editing controls so their constraints stay aligned."""
    p = existing or {}
    name = st.text_input('Field name', value=p.get('name', ''), key=prefix + '_name')
    crop_options = list(CROPS)
    crop = st.selectbox('Crop', crop_options, index=crop_options.index(p['crop']) if p.get('crop') in crop_options else 0,
                        format_func=lambda x: CROPS[x], key=prefix + '_crop')
    seasons = list(router().seasons(crop))
    season = st.selectbox('Season', seasons, index=seasons.index(p['season']) if p.get('season') in seasons else 0, key=prefix + '_season')
    districts = sorted(DISTRICT_NAMES, key=lambda x: DISTRICT_NAMES[x])
    district = st.selectbox('District', districts, index=districts.index(p['district']) if p.get('district') in districts else 0,
                            format_func=lambda x: DISTRICT_NAMES[x], key=prefix + '_district')
    area = st.number_input('Area (hectares)', min_value=.001, value=max(float(p.get('area_ha', .2)), .001), step=.05, format='%.3f', key=prefix + '_area')
    types = ['1', '2']
    farmer_type = st.selectbox('Farmer type', types, index=types.index(p.get('farmer_type', '1')) if p.get('farmer_type', '1') in types else 0,
                               format_func=lambda x: {'1': 'Small-scale individual', '2': 'Small-scale organization'}[x], key=prefix + '_farmer')
    old_seed = p.get('seed_type', 'Not sure')
    seed_type = st.selectbox('Seed variety', SEED_TYPES, index=SEED_TYPES.index(old_seed) if old_seed in SEED_TYPES else 2, key=prefix + '_seed')
    old_fert = p.get('fertilizer_type', 'None / not applied')
    fertilizer = st.selectbox('Fertilizer used', FERTILIZER_TYPES, index=FERTILIZER_TYPES.index(old_fert) if old_fert in FERTILIZER_TYPES else 2, key=prefix + '_fert')
    planted = st.date_input('Planting date (optional)', value=date.fromisoformat(p['planted']) if p.get('planted') else None, key=prefix + '_planted')
    return (name.strip(), crop, season, district, float(area), farmer_type, planted.isoformat() if planted else None, seed_type, fertilizer)


def my_plots(u: dict) -> None:
    hero('My Fields', 'Register, review and edit your cultivated areas, crop inputs and seasons.', 'fields.jpg', 'FARMER / FIELDS')
    with st.expander('Register a field', expanded=False):
        with st.form('plot_create'):
            values = field_inputs('create')
            ok = st.form_submit_button('Save field', type='primary')
        if ok:
            if not values[0]:
                st.error('A field name is required.')
            else:
                execute('INSERT INTO plots(user_id,name,crop,season,district,area_ha,farmer_type,planted,seed_type,fertilizer_type) VALUES(?,?,?,?,?,?,?,?,?,?)',
                        (u['id'], *values))
                st.success('Field saved.')
                st.rerun()

    rows = plots(u['id'])
    if not rows:
        st.info('No fields registered yet.')
        return
    for p in rows:
        with st.container(border=True):
            a, b, c = st.columns([5, 1, 1])
            a.markdown(f"**{html.escape(p['name'])}**")
            a.caption(f"{CROPS.get(p['crop'],p['crop'])} · Season {p['season']} · {DISTRICT_NAMES.get(p['district'],p['district'])} · {p['area_ha']:.3f} ha")
            a.caption(f"Seeds: {p['seed_type']} · Fertilizer: {p['fertilizer_type']}")
            if b.button('Edit', key='editplot' + str(p['id'])):
                st.session_state['editplot'] = None if st.session_state.get('editplot') == p['id'] else p['id']
            if c.button('Delete', key='delplot' + str(p['id'])):
                st.session_state['deleteplot'] = p['id']
            if st.session_state.get('editplot') == p['id']:
                st.info('Changing crop, area or season does not automatically recalculate saved estimates. Run Harvest Estimator again after saving.')
                with st.form('edit_form_' + str(p['id'])):
                    updated = field_inputs('edit_' + str(p['id']), p)
                    save_edit = st.form_submit_button('Save changes', type='primary')
                if save_edit:
                    if not updated[0]:
                        st.error('A field name is required.')
                    else:
                        execute('UPDATE plots SET name=?,crop=?,season=?,district=?,area_ha=?,farmer_type=?,planted=?,seed_type=?,fertilizer_type=? WHERE id=? AND user_id=?', (*updated, p['id'], u['id']))
                        st.session_state['editplot'] = None
                        st.success('Field updated.')
                        st.rerun()
            if st.session_state.get('deleteplot') == p['id']:
                st.warning('This permanently deletes the field and all associated estimates, monitoring, activities and financial entries.')
                if st.button('Confirm deletion', key='confirm' + str(p['id'])):
                    with db() as connection:
                        for table in ('forecasts', 'checkins', 'tasks', 'ledger'):
                            connection.execute(f'DELETE FROM {table} WHERE plot_id=? AND user_id=?', (p['id'], u['id']))
                        connection.execute('DELETE FROM plots WHERE id=? AND user_id=?', (p['id'], u['id']))
                    st.session_state['deleteplot'] = None
                    st.rerun()


def forecast(u: dict) -> None:
    hero('Harvest Estimator', 'Generate a model-based production range from a registered field.', 'hero.jpg', 'FARMER / ESTIMATION')
    p = pick_plot(u['id'], 'forecastplot')
    if p is None:
        return
    info, side = st.columns([1.45, 1], gap='large')
    with info:
        st.caption(f"{CROPS[p['crop']]} · Season {p['season']} · {p['area_ha']:.3f} ha · {DISTRICT_NAMES[p['district']]}")
        needs = router().catalog[p['crop']]['harvest_question']
        harvesting = st.radio('Do you expect to harvest this crop this season?', ['Yes', 'No'], horizontal=True) if needs else 'Yes'
        if st.button('Calculate harvest estimate', type='primary'):
            r = router().predict(
                p['crop'], p['season'], p['district'], p['farmer_type'],
                plot_area_ha=p['area_ha'],
                harvest_this_season=harvesting == 'Yes' if needs else None,
            )
            if r['status'] != 'ok':
                st.warning(f"Prediction not available: {r['status'].replace('_', ' ')}")
            else:
                execute(
                    'INSERT INTO forecasts(user_id,plot_id,estimate,lower,upper,evidence) VALUES(?,?,?,?,?,?)',
                    (u['id'], p['id'], r['estimate_kg'], r['lower_kg'], r['upper_kg'], r['evidence']),
                )
                st.session_state.setdefault('lastforecast', {})[p['id']] = r
                st.rerun()
    with side:
        r = st.session_state.get('lastforecast', {}).get(p['id'])
        if r and r.get('status') == 'ok':
            st.markdown('<div class="focus-panel">', unsafe_allow_html=True)
            st.metric('Estimated harvest', f"{r['estimate_kg']:,.0f} kg")
            st.caption(f"Range: {r['lower_kg']:,.0f}–{r['upper_kg']:,.0f} kg")
            st.caption(f"Evidence label: {r['evidence']}")
            st.markdown('</div>', unsafe_allow_html=True)
        else:
            st.info('Run the estimator to display a new result panel here.')
    rows = query('SELECT recorded_at,estimate,lower,upper FROM forecasts WHERE user_id=? AND plot_id=? ORDER BY id DESC LIMIT 20', (u['id'], p['id']))
    if rows:
        heading('Saved forecast history')
        st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)


def observations(u: dict) -> None:
    hero('Crop Monitoring', 'Save direct field observations and notes from your crop checks.', 'fields.jpg', 'FARMER / MONITORING')
    p = pick_plot(u['id'], 'checkplot')
    if p is None:
        return
    with st.form('checkin'):
        stage = st.selectbox('Growth stage', ['Preparation', 'Germination', 'Vegetative', 'Flowering', 'Maturing', 'Harvest'])
        condition = st.selectbox('Observed condition', ['Healthy', 'Needs attention', 'Uncertain'])
        note = st.text_area('Observation and actions taken', max_chars=1500)
        ok = st.form_submit_button('Save check-in', type='primary')
    if ok:
        execute('INSERT INTO checkins(user_id,plot_id,stage,condition,note) VALUES(?,?,?,?,?)', (u['id'], p['id'], stage, condition, note.strip()))
        st.success('Saved.')
        st.rerun()
    rows = query('SELECT created_at,stage,condition,note FROM checkins WHERE user_id=? AND plot_id=? ORDER BY id DESC', (u['id'], p['id']))
    if rows:
        st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)


def activities(u: dict) -> None:
    hero('Farm Activities', 'Record planned work and mark completed tasks as the season progresses.', 'weather.jpg', 'FARMER / ACTIVITIES')
    p = pick_plot(u['id'], 'taskplot')
    if p is None:
        return
    with st.form('taskform'):
        title = st.text_input('Activity', placeholder='e.g. Check for crop pests')
        due = st.date_input('Due date', value=date.today())
        save = st.form_submit_button('Add activity', type='primary')
    if save and title.strip():
        execute('INSERT INTO tasks(user_id,plot_id,title,due) VALUES(?,?,?,?)', (u['id'], p['id'], title.strip(), due.isoformat()))
        st.rerun()
    for t in query('SELECT * FROM tasks WHERE user_id=? AND plot_id=? ORDER BY done,due', (u['id'], p['id'])):
        overdue = not t['done'] and t['due'] and t['due'] < date.today().isoformat()
        status = '✅ Completed' if t['done'] else '🔴 Overdue' if overdue else '🟢 Upcoming'
        a, b = st.columns([6, 1])
        checked = a.checkbox(f"{status} · {t['title']} · {t['due'] or 'No due date'}", value=bool(t['done']), key='task' + str(t['id']))
        if checked != bool(t['done']):
            execute('UPDATE tasks SET done=? WHERE id=? AND user_id=? AND plot_id=?', (int(checked), t['id'], u['id'], p['id']))
            st.rerun()
        if b.button('Remove', key='task_delete_' + str(t['id'])):
            execute('DELETE FROM tasks WHERE id=? AND user_id=? AND plot_id=?', (t['id'], u['id'], p['id']))
            st.rerun()


def finances(u: dict) -> None:
    hero('Farm Finances', 'Track key expenses and sales linked to your fields.', 'planner.jpg', 'FARMER / FINANCES')
    p = pick_plot(u['id'], 'ledgerplot')
    if p is None:
        return
    with st.form('ledgerform'):
        a, b = st.columns(2)
        kind = a.selectbox('Record type', ['Expense', 'Sale'])
        amount = b.number_input('Amount in RWF', min_value=0., value=1000., step=500.)
        category = st.selectbox('Category', ['Seeds', 'Fertilizer', 'Transport', 'Labor', 'Harvest sale', 'Other'])
        day = st.date_input('Transaction date', value=date.today())
        note = st.text_input('Notes')
        ok = st.form_submit_button('Save entry', type='primary')
    if ok and amount > 0:
        execute('INSERT INTO ledger(user_id,plot_id,kind,amount,category,note,day) VALUES(?,?,?,?,?,?,?)', (u['id'], p['id'], kind, amount, category, note, day.isoformat()))
        st.rerun()
    rows = query('SELECT day,kind,amount,category,note FROM ledger WHERE user_id=? AND plot_id=? ORDER BY day DESC', (u['id'], p['id']))
    if rows:
        df = pd.DataFrame(rows)
        a, b, c = st.columns(3)
        sales = df.loc[df.kind == 'Sale', 'amount'].sum()
        cost = df.loc[df.kind == 'Expense', 'amount'].sum()
        a.metric('Recorded sales', f'{sales:,.0f} RWF')
        b.metric('Recorded costs', f'{cost:,.0f} RWF')
        c.metric('Recorded balance', f'{sales - cost:,.0f} RWF')
        st.plotly_chart(px.bar(df, x='day', y='amount', color='kind', barmode='group'), use_container_width=True)
        st.dataframe(df, hide_index=True, use_container_width=True)


def weather(u: dict) -> None:
    hero('District Weather', 'Use a short district forecast to support activity planning.', 'weather.jpg', 'FARMER / WEATHER')
    p = pick_plot(u['id'], 'weatherplot')
    if p is None:
        return
    st.write('Selected district:', DISTRICT_NAMES[p['district']])
    st.info('Forecast availability depends on the live Open-Meteo service. District reference locations are approximate.')
    points = ROOT / 'data' / 'district_weather_points.json'
    if points.exists():
        raw = json.loads(points.read_text())
        pt = raw.get('districts', {}).get(p['district']) if isinstance(raw, dict) else None
        if isinstance(pt, dict):
            lat = pt.get('latitude', pt.get('lat'))
            lon = pt.get('longitude', pt.get('lon'))
            if lat is not None and lon is not None:
                try:
                    response = requests.get(
                        'https://api.open-meteo.com/v1/forecast',
                        params={
                            'latitude': lat,
                            'longitude': lon,
                            'daily': 'temperature_2m_max,precipitation_sum,precipitation_probability_max',
                            'timezone': 'Africa/Kigali',
                            'forecast_days': 5,
                        },
                        timeout=10,
                    )
                    response.raise_for_status()
                    forecast = response.json()['daily']
                    df = pd.DataFrame({
                        'Date': forecast['time'],
                        'Max °C': forecast['temperature_2m_max'],
                        'Rain (mm)': forecast['precipitation_sum'],
                        'Rain probability (%)': forecast.get('precipitation_probability_max', [None] * len(forecast['time'])),
                    })
                    left, right = st.columns([1.15, .85], gap='large')
                    with left:
                        st.dataframe(df, hide_index=True, use_container_width=True)
                    with right:
                        st.line_chart(df.set_index('Date')['Max °C'])
                    st.caption('Weather source: Open-Meteo, using an approximate district reference point.')
                    return
                except (requests.RequestException, KeyError, ValueError):
                    pass
    st.warning('District weather data is unavailable for this location right now.')


def try_gemini(prompt: str) -> str | None:
    try:
        from google import genai
        key = os.getenv('GEMINI_API_KEY', '') or str(st.secrets.get('GEMINI_API_KEY', ''))
        if not key:
            return None
        client = genai.Client(api_key=key)
        response = client.models.generate_content(model='gemini-2.5-flash', contents=prompt)
        text = getattr(response, 'text', None)
        return text.strip() if text else None
    except Exception:
        return None


def heuristic_reply(role: str, question: str, context: str) -> str:
    q = question.lower()
    if 'weather' in q or 'rain' in q:
        return 'Use the District Weather page to check the next few days, then plan spraying, planting, or harvesting around rainfall and temperature changes. If rain is expected, avoid delaying urgent field inspections.'
    if 'yield' in q or 'harvest' in q or 'estimate' in q:
        return 'Open Harvest Estimator for the selected field, compare the estimated range with your own field condition, then adjust expectations using recent crop monitoring notes and activity completion.'
    if 'finance' in q or 'cost' in q or 'profit' in q or 'sale' in q:
        return 'Review Farm Finances and keep all expenses plus harvest sales recorded. A clearer cost record makes it easier to compare seasons and decide whether a field is still performing well.'
    if role == 'planner':
        return 'Use the filtered planner dashboards to identify which crops and districts have the most recorded area, then check where registration is still sparse before drawing strong conclusions.'
    return 'I can answer this question when the AI service is configured. Currently, offline guidance only covers basic field, harvest, weather and finance topics. Ask the app administrator to configure GEMINI_API_KEY.'


def assistant_page(u: dict) -> None:
    hero('AI Assistant', 'Ask for simple support using your TeraSmart records and the available context.', 'hero.jpg', f'{u["role"].upper()} / AI ASSISTANT')
    context_parts = []
    if u['role'] == 'farmer':
        p = pick_plot(u['id'], 'assistant_plot')
        if p:
            recent_checks = query('SELECT stage,condition,created_at FROM checkins WHERE user_id=? AND plot_id=? ORDER BY id DESC LIMIT 3', (u['id'], p['id']))
            recent_tasks = query('SELECT title,due,done FROM tasks WHERE user_id=? AND plot_id=? ORDER BY id DESC LIMIT 5', (u['id'], p['id']))
            recent_forecasts = query('SELECT estimate,lower,upper,recorded_at FROM forecasts WHERE user_id=? AND plot_id=? ORDER BY id DESC LIMIT 2', (u['id'], p['id']))
            context_parts.append(f"Field: {p['name']}, crop {CROPS[p['crop']]}, season {p['season']}, district {DISTRICT_NAMES[p['district']]}, area {p['area_ha']:.3f} ha.")
            if recent_forecasts:
                f0 = recent_forecasts[0]
                context_parts.append(f"Latest estimate {f0['estimate']:.0f} kg with range {f0['lower']:.0f}-{f0['upper']:.0f} kg.")
            if recent_checks:
                context_parts.append('Recent crop observations: ' + '; '.join(f"{x['stage']} / {x['condition']}" for x in recent_checks) + '.')
            if recent_tasks:
                context_parts.append('Recent activities: ' + '; '.join(f"{x['title']} ({'done' if x['done'] else 'pending'})" for x in recent_tasks) + '.')
        suggestions = [
            'What should I focus on this week for this field?',
            'How should I interpret my latest harvest estimate?',
            'What records should I update to improve decisions?'
        ]
    else:
        summary = query('SELECT crop,season,district,area_ha FROM plots')
        if summary:
            df = pd.DataFrame(summary)
            context_parts.append(f"Total registered fields: {len(df)}. Total area: {df['area_ha'].sum():.2f} ha.")
            context_parts.append('Most represented crops: ' + ', '.join(df['crop'].map(CROPS).value_counts().head(4).index.tolist()) + '.')
        suggestions = [
            'Summarize the current crop registration pattern.',
            'What planning caution should I keep in mind with this data?',
            'How can I use these records responsibly in a report?'
        ]

    heading('Suggested prompts')
    cols = st.columns(len(suggestions))
    for i, s in enumerate(suggestions):
        if cols[i].button(s, key=f'suggest_{u["role"]}_{i}', use_container_width=True):
            st.session_state['assistant_prompt'] = s

    st.caption('Ask about your fields or any general topic. For live, open-ended AI answers, configure a Gemini API key; otherwise limited offline farm tips are available.')
    question = st.text_area('Your question', value=st.session_state.get('assistant_prompt', ''), placeholder='Ask for help interpreting your records or planning next actions.', height=120)
    if st.button('Generate response', type='primary'):
        if not question.strip():
            st.warning('Type a question first.')
        else:
            context = '\n'.join(context_parts) if context_parts else 'No specific field context is available.'
            prompt = f"You are TeraSmart, a helpful general-purpose assistant with additional agricultural knowledge. Answer ANY safe question in clear, accurate English (including non-farming questions). When the user asks about their own farm or planner records, use the provided context, and never fabricate missing records. For unrelated general questions, use your general knowledge; do not restrict answers to the farm context. Admit uncertainty and avoid pretending to have live data. The following context is private to this logged-in user's role. Role: {u['role']}.\n\nAvailable context:\n{context}\n\nQuestion:\n{question.strip()}"
            reply = try_gemini(prompt) or heuristic_reply(u['role'], question, context)
            st.markdown('### Response')
            st.write(reply)
            st.caption('Use this as decision support only. It does not replace local agronomic judgement.')

    if context_parts:
        with st.expander('Context currently available to the assistant'):
            for item in context_parts:
                st.write('-', item)


def planner_overview() -> None:
    total = query("SELECT COUNT(*) AS n FROM users WHERE role='farmer'")[0]['n']
    plots_all = query('SELECT district,crop,season,area_ha FROM plots')
    a, b, c, d = st.columns(4)
    with a: stat_tile('Farmers', str(total), 'registered users')
    with b: stat_tile('Fields', str(len(plots_all)), 'field records')
    with c: stat_tile('Area', f"{sum(p['area_ha'] for p in plots_all):,.2f} ha", 'total recorded area')
    with d: stat_tile('Crops', str(len(set(p['crop'] for p in plots_all))), 'represented crops')
    if not plots_all:
        st.info('Once farmers register fields, their aggregated records will appear here.')
        return
    df = pd.DataFrame(plots_all)
    df['Crop'] = df.crop.map(CROPS)
    df['District'] = df.district.map(DISTRICT_NAMES)

    heading('Filter the current record base', 'Charts update from the records currently stored in TeraSmart')
    s1, s2, s3 = st.columns(3)
    crop_filter = s1.selectbox('Crop', ['All crops'] + sorted(df['Crop'].dropna().unique().tolist()), key='planner_crop_filter')
    season_filter = s2.selectbox('Season', ['All seasons'] + sorted(df['season'].dropna().unique().tolist()), key='planner_season_filter')
    district_filter = s3.selectbox('District', ['All districts'] + sorted(df['District'].dropna().unique().tolist()), key='planner_district_filter')
    if crop_filter != 'All crops':
        df = df[df['Crop'] == crop_filter]
    if season_filter != 'All seasons':
        df = df[df['season'] == season_filter]
    if district_filter != 'All districts':
        df = df[df['District'] == district_filter]
    if df.empty:
        st.info('No records match these filters.')
        return

    top, bottom = st.columns([1.1, .9], gap='large')
    with top:
        heading('Area concentration by district')
        by_district = df.groupby('District', as_index=False).area_ha.sum().sort_values('area_ha', ascending=False)
        fig = px.bar(by_district, x='District', y='area_ha', color_discrete_sequence=['#62875A'], labels={'area_ha': 'Area (ha)'})
        fig.update_layout(height=350, showlegend=False, margin=dict(l=6, r=8, t=5, b=24), paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
        st.plotly_chart(fig, use_container_width=True)
    with bottom:
        heading('Crop mix in the filtered records')
        by_crop = df.groupby('Crop', as_index=False).area_ha.sum()
        fig = px.pie(by_crop, names='Crop', values='area_ha', hole=.55, color_discrete_sequence=['#62875A', '#9AB883', '#C59B5B', '#41664A', '#B3A17B'])
        fig.update_layout(height=350, margin=dict(l=8, r=8, t=5, b=20), paper_bgcolor='rgba(0,0,0,0)')
        st.plotly_chart(fig, use_container_width=True)

    heading('District summary table', 'Names and phone numbers are not shown in planner views')
    grouped = df.groupby('District', as_index=False).agg(Fields=('area_ha', 'size'), **{'Area (ha)': ('area_ha', 'sum')})
    st.dataframe(grouped.sort_values('Area (ha)', ascending=False), hide_index=True, use_container_width=True)
    st.download_button(
        'Export summary as CSV',
        grouped.to_csv(index=False).encode('utf-8'),
        file_name='terasmart_district_summary.csv',
        mime='text/csv',
        use_container_width=True,
    )
    st.caption('Planner outputs summarize user-entered registrations only and are not nationally representative statistics.')



def latest_forecasts() -> pd.DataFrame:
    """One saved estimate per plot; do not sum repeat predictions for the same field."""
    rows = query("""
        SELECT p.id AS plot_id, p.crop, p.district, p.season, p.area_ha,
               f.estimate, f.lower, f.upper, f.recorded_at
        FROM plots p
        JOIN forecasts f ON f.id = (
            SELECT MAX(f2.id) FROM forecasts f2 WHERE f2.plot_id = p.id
        )
        WHERE p.crop IN ('101','106','110','103','107','108','111','122','123','305')
    """)
    if not rows:
        return pd.DataFrame(columns=['plot_id','crop','district','season','area_ha','estimate','lower','upper','recorded_at','Crop','District'])
    df = pd.DataFrame(rows)
    df['Crop'] = df['crop'].map(CROPS)
    df['District'] = df['district'].map(DISTRICT_NAMES)
    return df


def forecast_filters(df: pd.DataFrame, prefix: str) -> pd.DataFrame:
    a,b,c = st.columns(3)
    crop = a.selectbox('Crop', ['All crops'] + sorted(df['Crop'].dropna().unique()), key=prefix+'_crop')
    district = b.selectbox('District', ['All districts'] + sorted(df['District'].dropna().unique()), key=prefix+'_district')
    season = c.selectbox('Season', ['All seasons'] + sorted(df['season'].dropna().unique()), key=prefix+'_season')
    if crop != 'All crops': df = df[df['Crop'] == crop]
    if district != 'All districts': df = df[df['District'] == district]
    if season != 'All seasons': df = df[df['season'] == season]
    return df


def forecast_summary(df: pd.DataFrame) -> pd.DataFrame:
    return df.groupby(['District','Crop','season'], as_index=False).agg(
        Fields=('plot_id','nunique'),
        **{'Registered area (ha)': ('area_ha','sum'),
           'Estimated harvest (kg)': ('estimate','sum'),
           'Indicative lower (kg)': ('lower','sum'),
           'Indicative upper (kg)': ('upper','sum')}
    ).sort_values('Estimated harvest (kg)', ascending=False)


def planner_production() -> None:
    hero('Production Forecasts',
         'Explore the combined latest harvest estimates from registered fields, by crop, district and season.',
         'fields.jpg', 'PLANNER / PRODUCTION')
    df = latest_forecasts()
    if df.empty:
        st.info('No saved farmer harvest estimates yet. Forecast totals will appear after farmers run the estimator.')
        return
    heading('Select your planning view', 'Each field contributes only its most recent saved estimate')
    df = forecast_filters(df, 'production')
    if df.empty:
        st.info('No saved estimates match the selected filters.')
        return
    a,b,c = st.columns(3)
    with a: stat_tile('Estimated harvest', f"{df['estimate'].sum():,.0f} kg", 'latest estimate per field')
    with b: stat_tile('Fields with estimates', str(df['plot_id'].nunique()), 'in current selection')
    with c: stat_tile('Registered area', f"{df['area_ha'].sum():,.2f} ha", 'of forecasted fields')
    x,y = st.columns([1.35, .85],gap='large')
    with x:
        heading('Projected production by crop')
        by_crop = df.groupby('Crop',as_index=False)['estimate'].sum().sort_values('estimate',ascending=True)
        fig = px.bar(by_crop, x='estimate',y='Crop',orientation='h',
                     labels={'estimate':'Estimated harvest (kg)'},color_discrete_sequence=['#62875A'])
        fig.update_layout(height=max(320, len(by_crop)*45), margin=dict(l=5,r=12,t=5,b=15),
                          paper_bgcolor='rgba(0,0,0,0)',plot_bgcolor='rgba(0,0,0,0)')
        st.plotly_chart(fig,use_container_width=True)
    with y:
        heading('Forecast coverage')
        fields_total = query('SELECT COUNT(*) AS n FROM plots')[0]['n']
        covered = query('SELECT COUNT(DISTINCT plot_id) AS n FROM forecasts')[0]['n']
        st.metric('Fields with estimates (all data)',f'{covered:,} / {fields_total:,}')
        st.caption('Coverage measures model use among registered fields, not national forecast coverage.')
        st.metric('Indicative combined range',f"{df['lower'].sum():,.0f}–{df['upper'].sum():,.0f} kg")
        st.caption('This is the sum of field-level indicative bounds, not a calibrated aggregate confidence interval.')
    heading('Production breakdown', 'Aggregated records — no individual farmer identifiers')
    table = forecast_summary(df)
    st.dataframe(table,hide_index=True,use_container_width=True)
    st.download_button('Download forecast table (CSV)',table.to_csv(index=False).encode('utf-8'),
                       file_name='terasmart_production_forecasts.csv',mime='text/csv')
    st.caption('Only fields with saved estimates appear. These are historical model outputs from participating users, not official district or national forecasts.')


def planner_reports() -> None:
    hero('Planning Reports',
         'Prepare a concise, filterable production and registration report for planning discussions.',
         'planner.jpg','PLANNER / REPORTS')
    raw = query('SELECT id,crop,district,season,area_ha FROM plots')
    if not raw:
        st.info('No registered fields yet. Reports become available when farmers add plots.')
        return
    base = pd.DataFrame(raw)
    base['Crop'] = base['crop'].map(CROPS)
    base['District'] = base['district'].map(DISTRICT_NAMES)
    heading('Report scope')
    c1,c2,c3=st.columns(3)
    crop=c1.selectbox('Crop',['All crops']+sorted(base['Crop'].dropna().unique()),key='report_crop')
    district=c2.selectbox('District',['All districts']+sorted(base['District'].dropna().unique()),key='report_district')
    season=c3.selectbox('Season',['All seasons']+sorted(base['season'].dropna().unique()),key='report_season')
    if crop!='All crops': base=base[base['Crop']==crop]
    if district!='All districts': base=base[base['District']==district]
    if season!='All seasons': base=base[base['season']==season]
    if base.empty:
        st.info('No records match these report filters.')
        return
    estimates=latest_forecasts()
    estimates=estimates[estimates['plot_id'].isin(base['id'])]
    a,b,c=st.columns(3)
    with a: stat_tile('Registered fields',str(len(base)),'matching filters')
    with b: stat_tile('Registered area',f"{base['area_ha'].sum():,.2f} ha",'matching filters')
    with c: stat_tile('Fields forecasted',str(len(estimates)),'latest estimate only')
    summary=base.groupby(['District','Crop','season'],as_index=False).agg(
        **{'Registered fields':('id','nunique'),'Registered area (ha)':('area_ha','sum')})
    if estimates.empty:
        summary['Fields with forecasts']=0
        summary['Estimated harvest (kg)']=0.0
    else:
        fsum=estimates.groupby(['District','Crop','season'],as_index=False).agg(
            **{'Fields with forecasts':('plot_id','nunique'),'Estimated harvest (kg)':('estimate','sum')})
        summary=summary.merge(fsum,on=['District','Crop','season'],how='left').fillna({'Fields with forecasts':0,'Estimated harvest (kg)':0})
    summary=summary.sort_values(['District','Crop','season'])
    heading('Report preview', 'User-entered field registrations and latest saved estimates')
    st.dataframe(summary,hide_index=True,use_container_width=True)
    today=date.today().isoformat()
    scope=f'Crop: {crop}; District: {district}; Season: {season}'
    coverage=100*len(estimates)/len(base)
    top=summary.sort_values('Estimated harvest (kg)',ascending=False).head(3)
    highlights='\n'.join(f"- {r['District']} / {r['Crop']} / Season {r['season']}: {r['Estimated harvest (kg)']:,.0f} kg from {int(r['Fields with forecasts'])} forecasted fields" for _,r in top.iterrows())
    report=(f'# TeraSmart Planning Report\n\nGenerated: {today}\n\n## Scope\n{scope}\n\n'
            f'## Key indicators\n- Registered fields: {len(base)}\n- Registered area: {base["area_ha"].sum():,.2f} ha\n'
            f'- Fields with saved harvest estimates: {len(estimates)} ({coverage:.1f}% of filtered fields)\n'
            f'- Combined estimated harvest (forecasted fields only): {estimates["estimate"].sum():,.0f} kg\n\n'
            f'## Highest recorded production estimates\n{highlights if len(estimates) else "No saved forecasts in this selection."}\n\n'
            '## Interpretation and limitations\nThese statistics describe fields registered by TeraSmart users. '
            'They are not representative district or national statistics. Only each field’s latest saved prediction is counted. '
            'Forecasts are model estimates and not guaranteed harvests. Fields without estimates are omitted from predicted production totals. '
            'Use these figures as preliminary planning indicators, not as official forecasts.\n')
    st.download_button('Download planning report (Markdown)',report.encode('utf-8'),
                       file_name=f'terasmart_planning_report_{today}.md',mime='text/markdown',use_container_width=True)
    st.download_button('Download report data (CSV)',summary.to_csv(index=False).encode('utf-8'),
                       file_name=f'terasmart_planning_data_{today}.csv',mime='text/csv',use_container_width=True)
    st.caption('Report contains aggregated values only, without names or phone numbers. Small-group re-identification still requires care.')


def planner_seasons() -> None:
    hero('Season & Crop Trends', 'Compare how the currently registered fields are distributed across crops and seasons.', 'planner.jpg', 'PLANNER / TRENDS')
    rows = query('SELECT crop,season,area_ha,district FROM plots')
    if not rows:
        st.info('No registered field data yet.')
        return
    df = pd.DataFrame(rows)
    df['Crop'] = df.crop.map(CROPS)
    fig = px.bar(
        df.groupby(['Crop', 'season'], as_index=False).area_ha.sum(),
        x='Crop', y='area_ha', color='season', barmode='group',
        labels={'area_ha': 'Area (ha)', 'season': 'Season'},
        color_discrete_sequence=['#62875A', '#A9B982', '#C59B5B']
    )
    fig.update_layout(height=410, margin=dict(l=8, r=8, t=12, b=12), paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
    st.plotly_chart(fig, use_container_width=True)
    st.caption('Observed registration totals only.')


def data_sources() -> None:
    hero('About Data Sources', 'Understand where TeraSmart gets its estimates and support information.', 'planner.jpg', 'DATA SOURCES / LIMITATIONS')
    a, b, c = st.columns(3)
    a.metric('Supported crops', len(CROPS))
    b.metric('Prediction models', 2)
    c.metric('Weather provider', 'Open-Meteo')
    heading('Primary data sources')
    left, right = st.columns(2, gap='large')
    with left:
        source_card(
            'NISR Seasonal Agricultural Survey 2025',
            'Historical agricultural observations',
            'The harvest prediction layer is built from previously trained models that were developed from SAS 2025 agricultural records. TeraSmart reuses those frozen models for demonstration.',
            'https://www.statistics.gov.rw/'
        )
    with right:
        source_card(
            'Open-Meteo',
            'Weather forecast service',
            'District weather uses approximate district reference coordinates to retrieve short forecasts from Open-Meteo. Conditions at a specific farm may differ.',
            'https://open-meteo.com/'
        )
    heading('How to interpret outputs')
    st.markdown(
        'Harvest estimates are **statistical predictions** based on crop, season, district, farmer type and cultivated area. '
        'They should be treated as indicative decision-support values, not guarantees. Crop observations, activities and finances are all entered by users and may be incomplete.'
    )
    st.info('The AI Assistant uses available TeraSmart context and, when configured, may also use Gemini. Responses should be treated as supportive guidance rather than authoritative agronomic advice.')
    with st.expander('Privacy and scope notes'):
        st.write('Planner pages show only aggregated records and do not display farmer names or phone numbers. Local SQLite storage may be temporary on cloud hosting. Avoid entering sensitive real-world personal data in a demo environment.')


def main() -> None:
    initialize()
    u = user()
    if u is None:
        gate()
        return

    farmer_nav = ['Overview', 'My Fields', 'Harvest Estimator', 'Crop Monitoring', 'Farm Activities', 'Farm Finances', 'District Weather', 'AI Assistant', 'Data Sources']
    planner_nav = ['Overview', 'Production Forecasts', 'Season & Crop Trends', 'Planning Reports', 'AI Assistant', 'Data Sources']
    nav = farmer_nav if u['role'] == 'farmer' else planner_nav
    active = st.session_state.get('page', 'Overview')
    if active not in set(nav):
        active = 'Overview'

    with st.sidebar:
        st.markdown('<div class="sidebar-brand"><div><strong>TeraSmart</strong><span>PLANT WITH INSIGHT</span></div></div>', unsafe_allow_html=True)
        st.markdown(f'<div class="user-chip"><span>{"FARMER" if u["role"] == "farmer" else "PLANNER"} PORTAL</span><strong>{u["name"]}</strong></div>', unsafe_allow_html=True)
        st.caption('NAVIGATION')
        for title in nav:
            kind = 'primary' if title == active else 'secondary'
            if st.button(title, key='nav_' + title, type=kind, use_container_width=True):
                st.session_state.page = title
                st.rerun()
        st.divider()
        if st.button('Sign out', use_container_width=True, key='logout'):
            st.session_state.user_id = None
            st.session_state.page = 'Overview'
            st.session_state.pop('lastforecast', None)
            st.session_state.pop('assistant_prompt', None)
            st.rerun()
        st.caption('TeraSmart · Demonstration release')

    routes = {
        'Overview': lambda: overview(u),
        'My Fields': lambda: my_plots(u),
        'Harvest Estimator': lambda: forecast(u),
        'Crop Monitoring': lambda: observations(u),
        'Farm Activities': lambda: activities(u),
        'Farm Finances': lambda: finances(u),
        'District Weather': lambda: weather(u),
        'AI Assistant': lambda: assistant_page(u),
        'Production Forecasts': planner_production,
        'Season & Crop Trends': planner_seasons,
        'Planning Reports': planner_reports,
        'Data Sources': data_sources,
    }
    routes[active]()


if __name__ == '__main__':
    main()
