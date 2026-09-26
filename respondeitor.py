import time

import streamlit as st
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
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

MAX_PARTS = 10          # límite de seguridad por cuestionario
MAX_CREDITS = 200        # límite de seguridad de créditos a procesar


# =========================================================
# DATOS DE LOGIN
# =========================================================

email = st.text_input("Email de DynaMed")

password = st.text_input("Contraseña de DynaMed", type="password")


# =========================================================
# FUNCIONES AUXILIARES
# =========================================================

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

    if not visible_candidates:
        return False

    return click_action(driver, visible_candidates[0])


def click_prepare_button(driver):
    """Busca y pulsa el botón Prepare de un crédito disponible.
    Devuelve True si se pulsó algún botón."""

    candidates = driver.find_elements(
        By.XPATH,
        "//*[normalize-space()='Prepare']"
    )

    visible_candidates = [
        e for e in candidates
        if e.is_displayed() and e.is_enabled()
    ]

    if not visible_candidates:
        return False

    return click_action(driver, visible_candidates[0])


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


def process_one_questionnaire(driver, status):

    total_other = 0
    total_not_found = 0

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

    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")
    options.binary_location = "/usr/bin/chromium"
    
    driver = webdriver.Chrome(
        options=options,
        service=webdriver.chrome.service.Service("/usr/bin/chromedriver")
)

    # =====================================================
    # LOGIN DYNAMED (automático, igual que Pregunteitor)
    # =====================================================

    st.info("Abriendo DynaMed...")

    driver.get(LOGIN_URL)

    time.sleep(5)


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

        st.error("No se encontró el botón Continue de login.")

        driver.quit()

        st.stop()

    click_js(driver, login_button)

    time.sleep(8)

    st.success("Login realizado correctamente.")


    # =====================================================
    # AVAILABLE CREDITS
    # =====================================================

    st.info("Abriendo Available Credits...")

    driver.get(AVAILABLE_CREDITS_URL)

    try:

        WebDriverWait(driver, PAGE_TIMEOUT).until(
            EC.presence_of_element_located(
                (By.CSS_SELECTOR, "[data-element='tabPanels']")
            )
        )

    except Exception as e:

        st.error("No se pudo cargar la página de Available Credits.")

        st.exception(e)

        driver.quit()

        st.stop()

    time.sleep(2)

    select_all_credits(driver)

    st.success("Opción 'All' seleccionada.")


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

        prepared = click_prepare_button(driver)

        if not prepared:

            st.write("No quedan más créditos disponibles. Fin.")

            break

        status.write("· Botón Prepare pulsado, esperando cuestionario...")

        try:

            WebDriverWait(driver, 20).until(
                lambda d: "questionnaire" in d.current_url.lower()
            )

        except Exception:

            status.write(
                "⚠ No se detectó el cuestionario tras pulsar Prepare. "
                "Se pasa al siguiente crédito."
            )

            driver.get(AVAILABLE_CREDITS_URL)

            time.sleep(3)

            select_all_credits(driver)

            continue

        o, nf = process_one_questionnaire(driver, status)

        grand_total_other += o
        grand_total_not_found += nf

        total_credits_done += 1

        st.write(
            f"✓ Crédito completado. Other: {o} · "
            f"I did not find...: {nf}"
        )

        # Volver a Available Credits para buscar el siguiente
        driver.get(AVAILABLE_CREDITS_URL)

        try:

            WebDriverWait(driver, PAGE_TIMEOUT).until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, "[data-element='tabPanels']")
                )
            )

        except Exception:
            pass

        time.sleep(2)

        select_all_credits(driver)


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
