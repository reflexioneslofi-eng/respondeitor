import time

import streamlit as st
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import StaleElementReferenceException


st.set_page_config(
    page_title="Respondeitor",
    page_icon="🎓"
)

st.title("🎓 Respondeitor")

st.write(
    "Reclama automáticamente todos los créditos CME/CPD/CE "
    "disponibles en DynaMed."
)


# =========================================================
# CONFIGURACIÓN
# =========================================================

LOGIN_URL = "https://www.dynamed.com"

AVAILABLE_CREDITS_URL = "https://www.dynamed.com/cme/available-credits"

PAGE_TIMEOUT = 60

OTHER_TEXT = "Other"

NOT_FOUND_TEXT = (
    "I did not find that the information answered my clinical question"
)

MAX_PARTS = 10           # límite de seguridad por cuestionario
MAX_CREDITS = 200        # límite de seguridad de créditos a procesar

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


# =========================================================
# DATOS DE LOGIN
# =========================================================

email = st.text_input("Email de DynaMed")

password = st.text_input("Contraseña de DynaMed", type="password")

debug = st.checkbox("Modo debug (mostrar capturas de pantalla)", value=True)


# =========================================================
# FUNCIONES AUXILIARES
# =========================================================

def snap(driver, caption):
    """Muestra una captura de pantalla en Streamlit (solo en modo debug)."""

    if not debug:
        return

    try:
        st.image(driver.get_screenshot_as_png(), caption=caption)
    except Exception:
        pass


def click_js(driver, elem):

    driver.execute_script(
        "arguments[0].scrollIntoView({block:'center'});",
        elem
    )

    driver.execute_script("arguments[0].click();", elem)


def click_action(driver, elem):
    """Click 'real' vía ActionChains. Si el elemento queda stale
    justo después (porque React ya reaccionó al click), lo
    consideramos un éxito."""

    try:

        driver.execute_script(
            "arguments[0].scrollIntoView({block:'center'});",
            elem
        )

        time.sleep(0.3)

        ActionChains(driver).move_to_element(elem).click().perform()

        return True

    except StaleElementReferenceException:

        return True

    except Exception:

        return False


def select_other_and_not_found(driver, max_idle_passes=3):

    other_selected = 0
    not_found_selected = 0

    processed = set()

    scroll_step = 150

    current_y = 0

    idle_passes = 0

    while True:

        found_new_this_pass = False

        labels = driver.find_elements(By.TAG_NAME, "label")

        for label in labels:

            try:

                text = label.text.strip()

                if text not in (OTHER_TEXT, NOT_FOUND_TEXT):
                    continue

                unique_key = label.get_attribute("for")

                if not unique_key:
                    unique_key = (
                        text + "_" + str(round(label.location["y"]))
                    )

                if unique_key in processed:
                    continue

                processed.add(unique_key)

                click_js(driver, label)

                time.sleep(0.05)

                found_new_this_pass = True

                if text == OTHER_TEXT:
                    other_selected += 1
                else:
                    not_found_selected += 1

            except Exception:
                pass

        max_height = driver.execute_script(
            "return document.body.scrollHeight"
        )

        at_bottom = current_y >= max_height

        current_y += scroll_step

        driver.execute_script(f"window.scrollTo(0,{current_y});")

        time.sleep(0.25)

        if at_bottom:

            if found_new_this_pass:
                idle_passes = 0
            else:
                idle_passes += 1

            if idle_passes >= max_idle_passes:
                break

    return other_selected, not_found_selected


def click_advance_button(driver):
    """Busca y pulsa el botón Continue/Submit del cuestionario."""

    candidates = driver.find_elements(
        By.XPATH,
        "//button[contains(@aria-label, 'Continue') "
        "or contains(@aria-label, 'Submit') "
        "or normalize-space()='Continue' "
        "or normalize-space()='Submit']"
    )

    visible_candidates = [
        e for e in candidates
        if e.is_displayed() and e.is_enabled()
    ]

    for elem in visible_candidates:
        if click_action(driver, elem):
            return True

    return False


def click_prepare_button(driver):
    """Prueba todos los candidatos 'Prepare' visibles hasta que uno
    funcione (igual que en la versión de Jupyter)."""

    candidates = driver.find_elements(
        By.XPATH,
        "//*[normalize-space()='Prepare']"
    )

    visible_candidates = [
        e for e in candidates
        if e.is_displayed() and e.is_enabled()
    ]

    for elem in visible_candidates:
        if click_action(driver, elem):
            return True

    return False


def wait_for_questionnaire(driver, handles_before, timeout=20):
    """Espera a que aparezca el cuestionario. Si se abrió una pestaña
    nueva, cambia a ella automáticamente."""

    def _ready(d):

        nuevas = [h for h in d.window_handles if h not in handles_before]

        if nuevas:
            d.switch_to.window(nuevas[-1])

        return "questionnaire" in d.current_url.lower()

    WebDriverWait(driver, timeout).until(_ready)


def close_extra_tabs(driver, main_handle):
    """Cierra todas las pestañas salvo la principal y vuelve a ella."""

    for h in list(driver.window_handles):

        if h != main_handle:

            try:
                driver.switch_to.window(h)
                driver.close()
            except Exception:
                pass

    driver.switch_to.window(main_handle)


def select_all_credits(driver):

    all_candidates = driver.find_elements(
        By.XPATH,
        "//*[normalize-space()='All']"
    )

    for elem in all_candidates:

        try:
            click_js(driver, elem)
            return True
        except Exception:
            pass

    return False


def open_available_credits(driver):
    """Abre Available Credits, espera a que cargue y selecciona 'All'."""

    driver.get(AVAILABLE_CREDITS_URL)

    WebDriverWait(driver, PAGE_TIMEOUT).until(
        EC.presence_of_element_located(
            (By.CSS_SELECTOR, "[data-element='tabPanels']")
        )
    )

    time.sleep(2)

    select_all_credits(driver)

    time.sleep(1)


def process_one_questionnaire(driver, status):

    total_other = 0
    total_not_found = 0

    # Igual que en Jupyter: dar tiempo a que renderice el cuestionario
    time.sleep(3)

    for part in range(1, MAX_PARTS + 1):

        status.write(f"  · Procesando parte {part}...")

        o, nf = select_other_and_not_found(driver)

        total_other += o
        total_not_found += nf

        time.sleep(0.5)

        advanced = click_advance_button(driver)

        if not advanced:
            status.write("  · No hay botón de avance, cuestionario terminado.")
            break

        time.sleep(3)

        if "questionnaire" not in driver.current_url.lower():
            status.write("  · ✓ Cuestionario completado.")
            break

    return total_other, total_not_found


# =========================================================
# BOTÓN
# =========================================================

if st.button("🚀 Ejecutar Respondeitor"):

    if not email or not password:

        st.warning("Introduce email y contraseña.")

        st.stop()


    # =====================================================
    # CHROME
    # =====================================================

    options = Options()

    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument(f"--user-agent={USER_AGENT}")
    options.binary_location = "/usr/bin/chromium"

    driver = webdriver.Chrome(
        options=options,
        service=Service("/usr/bin/chromedriver")
    )


    # =====================================================
    # LOGIN DYNAMED (automático)
    # =====================================================

    st.info("Abriendo DynaMed...")

    driver.get(LOGIN_URL)

    time.sleep(5)

    snap(driver, "1. Página inicial de DynaMed")


    # SIGN IN

    links = driver.find_elements(By.TAG_NAME, "a")

    for link in links:

        try:

            if "Sign In" in link.text.strip():

                click_js(driver, link)

                break

        except Exception:
            pass

    time.sleep(5)


    # COOKIES

    buttons = driver.find_elements(By.TAG_NAME, "button")

    for button in buttons:

        try:

            if button.text.strip() == "Accept":

                click_js(driver, button)

                time.sleep(2)

                break

        except Exception:
            pass


    # EMAIL

    try:

        username = driver.find_element(By.ID, "username")

        username.clear()

        username.send_keys(email)

    except Exception as e:

        snap(driver, "Error: no se encontró el campo de email")

        st.error("No se encontró el campo de email.")

        st.exception(e)

        driver.quit()

        st.stop()


    # CONTINUE EMAIL

    buttons = driver.find_elements(By.TAG_NAME, "button")

    for button in buttons:

        try:

            if button.text.strip() == "Continue":

                click_js(driver, button)

                break

        except Exception:
            pass

    time.sleep(5)


    # PASSWORD

    try:

        password_field = driver.find_element(By.ID, "password")

        password_field.clear()

        password_field.send_keys(password)

    except Exception as e:

        snap(driver, "Error: no se encontró el campo de contraseña")

        st.error("No se encontró el campo de contraseña.")

        st.exception(e)

        driver.quit()

        st.stop()


    # LOGIN

    buttons = driver.find_elements(By.TAG_NAME, "button")

    login_button = None

    for button in buttons:

        try:

            if button.text.strip() == "Continue":

                login_button = button

                break

        except Exception:
            pass

    if login_button is None:

        snap(driver, "Error: no se encontró el botón de login")

        st.error("No se encontró el botón Continue de login.")

        driver.quit()

        st.stop()

    click_js(driver, login_button)

    time.sleep(8)

    snap(driver, "2. Tras el login (¿captcha, MFA o error?)")

    st.success("Login realizado (revisa la captura por si hay captcha o MFA).")


    # =====================================================
    # AVAILABLE CREDITS
    # =====================================================

    st.info("Abriendo Available Credits...")

    try:

        open_available_credits(driver)

    except Exception as e:

        snap(driver, "Error al cargar Available Credits")

        st.error("No se pudo cargar la página de Available Credits.")

        st.exception(e)

        driver.quit()

        st.stop()

    snap(driver, "3. Available Credits con 'All' seleccionado")

    main_handle = driver.current_window_handle


    # =====================================================
    # PROCESAR TODOS LOS CRÉDITOS DISPONIBLES
    # =====================================================

    total_credits_done = 0
    grand_total_other = 0
    grand_total_not_found = 0

    for credit_number in range(1, MAX_CREDITS + 1):

        st.write("---")

        st.write(f"**Crédito {credit_number}**")

        status = st.empty()

        handles_before = list(driver.window_handles)

        if not click_prepare_button(driver):

            snap(driver, "No se encontró ningún botón Prepare")

            st.write("No quedan más créditos disponibles. Fin.")

            break

        status.write("· Botón Prepare pulsado, esperando cuestionario...")

        try:

            wait_for_questionnaire(driver, handles_before)

        except Exception:

            snap(driver, "Tras pulsar Prepare (no se detectó cuestionario)")

            status.write(
                "⚠ No se detectó el cuestionario tras pulsar Prepare. "
                "Se pasa al siguiente crédito."
            )

            try:
                close_extra_tabs(driver, main_handle)
                open_available_credits(driver)
            except Exception:
                pass

            continue

        o, nf = process_one_questionnaire(driver, status)

        grand_total_other += o
        grand_total_not_found += nf

        total_credits_done += 1

        st.write(
            f"✓ Crédito completado. Other: {o} · "
            f"I did not find...: {nf}"
        )

        # Cerrar pestaña extra (si la hay) y volver a la principal
        try:
            close_extra_tabs(driver, main_handle)
        except Exception:
            pass

        # Volver a Available Credits para buscar el siguiente
        try:
            open_available_credits(driver)
        except Exception:
            pass


    # =====================================================
    # RESUMEN FINAL
    # =====================================================

    st.write("---")

    st.success(
        f"🎉 Proceso terminado. Créditos completados: "
        f"{total_credits_done}"
    )

    st.write(
        f"Total 'Other' seleccionados: {grand_total_other}  \n"
        f"Total 'I did not find...' seleccionados: {grand_total_not_found}"
    )


    # =====================================================
    # CERRAR CHROME
    # =====================================================

    driver.quit()
