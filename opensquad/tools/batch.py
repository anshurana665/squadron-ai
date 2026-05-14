"""
opensquad/tools/batch.py
In-memory ZIP batch processor.
Extracts code files → runs agent pipeline → repackages into new ZIP.
Non-code files (images, fonts, etc.) are preserved unchanged.
"""
import io
import time
import zipfile
import streamlit as st

# File extensions that should be processed by the AI agents
CODE_EXTENSIONS = {".py", ".js", ".ts", ".jsx", ".tsx", ".html", ".css", ".java", ".cpp", ".c", ".go", ".rb"}

# Extensions to skip entirely (binary / non-text)
SKIP_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico", ".woff",
                   ".woff2", ".ttf", ".eot", ".pdf", ".zip", ".tar", ".gz",
                   ".mp4", ".mp3", ".wav", ".pyc", ".pyo", ".exe", ".dll"}


def _get_extension(filename: str) -> str:
    """Return lowercase file extension including dot."""
    if "." not in filename:
        return ""
    return "." + filename.rsplit(".", 1)[-1].lower()


def process_codebase_zip(
    uploaded_file,
    agent_runner_fn,
) -> io.BytesIO | None:
    """
    Process an uploaded ZIP file through the OpenSquad agent pipeline.

    Args:
        uploaded_file   : Streamlit UploadedFile (.zip)
        agent_runner_fn : Callable(code_str, filename) -> patched_code_str

    Returns:
        BytesIO of the new patched ZIP, or None on failure.
    """
    try:
        zip_bytes = io.BytesIO(uploaded_file.getvalue())
    except Exception as e:
        st.error(f"❌ Could not read uploaded file: {e}")
        return None

    # ── Scan ZIP contents first ──────────────────────────────────────
    try:
        with zipfile.ZipFile(zip_bytes, "r") as zin:
            all_names  = zin.namelist()
    except zipfile.BadZipFile:
        st.error("❌ Invalid ZIP file. Please upload a valid .zip archive.")
        return None

    # Count processable code files
    code_files = [
        name for name in all_names
        if _get_extension(name) in CODE_EXTENSIONS
        and not name.endswith("/")  # skip directories
    ]

    total   = len(code_files)
    skipped = len(all_names) - total

    if total == 0:
        st.warning("⚠️ No supported code files found in ZIP. Nothing to audit.")
        return None

    # ── UI setup ─────────────────────────────────────────────────────
    st.markdown("### 🔄 Batch Processing Progress")
    col1, col2, col3 = st.columns(3)
    col1.metric("📁 Code Files",    total)
    col2.metric("⏭️ Skipped Files", skipped)
    col3.metric("🏷️ Supported Types", ", ".join(sorted(CODE_EXTENSIONS)[:6]) + "…")

    progress_bar  = st.progress(0)
    status_text   = st.empty()
    results_table = []

    # ── Process ──────────────────────────────────────────────────────
    output_zip_buffer = io.BytesIO()

    zip_bytes.seek(0)   # reset cursor before second read
    with zipfile.ZipFile(zip_bytes, "r") as zin:
        with zipfile.ZipFile(output_zip_buffer, "w", zipfile.ZIP_DEFLATED) as zout:

            processed_count = 0

            for member_name in all_names:
                ext = _get_extension(member_name)

                # ── Directory entry — copy as-is ─────────────────────
                if member_name.endswith("/"):
                    try:
                        zout.mkdir(member_name)
                    except Exception:
                        pass
                    continue

                # ── Skip binary / non-code files ─────────────────────
                if ext in SKIP_EXTENSIONS or ext not in CODE_EXTENSIONS:
                    try:
                        zout.writestr(member_name, zin.read(member_name))
                    except Exception:
                        pass
                    continue

                # ── Process code file ─────────────────────────────────
                processed_count += 1
                progress = processed_count / total
                progress_bar.progress(progress)
                status_text.markdown(
                    f"🤖 **Processing** `{member_name}` "
                    f"({processed_count}/{total})"
                )

                start_time = time.time()
                try:
                    raw_bytes   = zin.read(member_name)
                    code_string = raw_bytes.decode("utf-8", errors="replace")

                    patched_code = agent_runner_fn(code_string, member_name)
                    elapsed      = round(time.time() - start_time, 1)

                    changed = (patched_code.strip() != code_string.strip())
                    results_table.append({
                        "file":    member_name,
                        "status":  "✅ Patched" if changed else "⏭️ No changes",
                        "time_s":  elapsed,
                    })

                    zout.writestr(member_name, patched_code.encode("utf-8"))

                except Exception as e:
                    elapsed = round(time.time() - start_time, 1)
                    st.warning(f"⚠️ `{member_name}` failed: {e} — keeping original.")
                    results_table.append({
                        "file":    member_name,
                        "status":  f"⚠️ Error: {str(e)[:60]}",
                        "time_s":  elapsed,
                    })
                    try:
                        zout.writestr(member_name, zin.read(member_name))
                    except Exception:
                        pass

    # ── Summary ──────────────────────────────────────────────────────
    progress_bar.progress(1.0)
    status_text.markdown("✅ **Batch processing complete!**")

    patched_count = sum(1 for r in results_table if "Patched" in r["status"])
    avg_time      = (
        sum(r["time_s"] for r in results_table) / len(results_table)
        if results_table else 0
    )

    st.markdown("### 📊 Audit Summary")
    c1, c2, c3 = st.columns(3)
    c1.metric("✅ Patched",         patched_count)
    c2.metric("📄 Total Processed", total)
    c3.metric("⏱️ Avg Time/File",   f"{avg_time:.1f}s")

    import pandas as pd
    df = pd.DataFrame(results_table)
    if not df.empty:
        st.dataframe(df, use_container_width=True)

    output_zip_buffer.seek(0)
    return output_zip_buffer
