// PianoForge desktop launcher.
// A tiny window-less host so Explorer, the taskbar and Alt+Tab can show the
// embedded icon; it just prepares the local environment and starts the GUI.
using System;
using System.Diagnostics;
using System.IO;

static class PianoForgeLauncher
{
    [STAThread]
    static void Main()
    {
        string root = Path.GetFullPath(AppDomain.CurrentDomain.BaseDirectory);
        try
        {
            string venvPy = Path.Combine(root, @".venv\Scripts\pythonw.exe");
            // A file carrying a "low integrity" label makes Windows run the whole
            // app restricted, which silently breaks shell integration (opening
            // folders). python_medium.txt names an unlabelled interpreter that can
            // still import this venv's packages.
            string pythonw = venvPy;
            string extraPath = "";
            string altFile = Path.Combine(root, "python_medium.txt");
            if (File.Exists(altFile))
            {
                string alt = File.ReadAllText(altFile).Trim();
                if (alt.Length > 0 && File.Exists(alt))
                {
                    pythonw = alt;
                    extraPath = ";" + Path.Combine(root, @".venv\Lib\site-packages");
                }
            }
            if (!File.Exists(pythonw))
                throw new FileNotFoundException("pythonw.exe not found", pythonw);

            ProcessStartInfo psi = new ProcessStartInfo(pythonw, "-m pianoforge.gui");
            psi.WorkingDirectory = root;
            psi.UseShellExecute = false;
            psi.CreateNoWindow = true;
            psi.EnvironmentVariables["PYTHONPATH"] = Path.Combine(root, "src") + extraPath;
            psi.EnvironmentVariables["PYTHONIOENCODING"] = "utf-8";
            psi.EnvironmentVariables["MPLCONFIGDIR"] = Path.Combine(root, @"cache\mpl");
            psi.EnvironmentVariables["TMP"] = Path.Combine(root, "tmp");
            psi.EnvironmentVariables["TEMP"] = Path.Combine(root, "tmp");
            psi.EnvironmentVariables["HF_ENDPOINT"] = "https://hf-mirror.com";
            psi.EnvironmentVariables["TORCH_HOME"] = Path.Combine(root, @"cache\torch");
            Process.Start(psi);
        }
        catch (Exception ex)
        {
            try
            {
                string dir = Path.Combine(root, "cache");
                Directory.CreateDirectory(dir);
                File.AppendAllText(Path.Combine(dir, "launcher_error.txt"),
                    DateTime.Now.ToString("s") + "  " + ex + Environment.NewLine);
            }
            catch { }
        }
    }
}
