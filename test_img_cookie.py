import streamlit as st

st.title("Inline Cookie Test App")

# Display cookies read from st.context.cookies
st.write("Cookies currently read by backend:", st.context.cookies)

if st.button("Set Test Cookie via Image"):
    st.markdown(
        '<img src="x" onerror="document.cookie=\'img_test_cookie=hello_from_image;path=/;max-age=86400;SameSite=Lax\'" style="display:none">',
        unsafe_allow_html=True
    )
    st.success("Set cookie html injected!")

if st.button("Erase Test Cookie via Image"):
    st.markdown(
        '<img src="x" onerror="document.cookie=\'img_test_cookie=;path=/;max-age=0;SameSite=Lax\'" style="display:none">',
        unsafe_allow_html=True
    )
    st.success("Erase cookie html injected!")
