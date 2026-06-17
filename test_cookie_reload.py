import streamlit as st
import streamlit.components.v1 as components

st.title("Cookie Reload Test App")

def set_cookie(name: str, value: str, ttl_days: int = 30, trigger_reload: bool = False):
    reload_js = "window.parent.location.reload();" if trigger_reload else ""
    components.html(
        f"""
        <script>
            var date = new Date();
            date.setTime(date.getTime() + ({ttl_days}*24*60*60*1000));
            var expires = "; expires=" + date.toUTCString();
            document.cookie = "{name}=" + "{value}" + expires + "; path=/; SameSite=Lax";
            {reload_js}
        </script>
        """,
        height=0,
    )

def erase_cookie(name: str, trigger_reload: bool = False):
    reload_js = "window.parent.location.reload();" if trigger_reload else ""
    components.html(
        f"""
        <script>
            document.cookie = "{name}=; Max-Age=0; path=/; SameSite=Lax";
            {reload_js}
        </script>
        """,
        height=0,
    )

# Display cookies read from st.context.cookies
st.write("Cookies currently read by backend:", st.context.cookies)

if st.button("Set Test Cookie & Reload"):
    set_cookie("reload_test_cookie", "hello_world_reload", trigger_reload=True)
    st.success("Set cookie and reload triggered!")

if st.button("Erase Test Cookie & Reload"):
    erase_cookie("reload_test_cookie", trigger_reload=True)
    st.success("Erase cookie and reload triggered!")
