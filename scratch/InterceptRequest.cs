using System;
using System.Net;
using System.Threading;
using System.Reflection;
using Countersoft.Gemini.Api;
using Countersoft.Gemini.Commons.Entity;

public class Program
{
    static Program()
    {
        AppDomain.CurrentDomain.AssemblyResolve += (sender, args) =>
        {
            string folderPath = @"C:\Users\d.batsilis\source\repos\dimitrisbatsi\GeminiBridge\GeminiBridge\libs\";
            string assemblyPath = System.IO.Path.Combine(folderPath, new AssemblyName(args.Name).Name + ".dll");
            if (System.IO.File.Exists(assemblyPath)) return Assembly.LoadFrom(assemblyPath);
            return null;
        };
    }

    public static void Main()
    {
        var listener = new HttpListener();
        listener.Prefixes.Add("http://localhost:9999/");
        listener.Start();
        
        var thread = new Thread(() =>
        {
            try
            {
                var context = listener.GetContext();
                var req = context.Request;
                Console.WriteLine("\n=== INTERCEPTED REQUEST ===");
                Console.WriteLine(req.HttpMethod + " " + req.Url);
                foreach (string header in req.Headers)
                {
                    Console.WriteLine(header + ": " + req.Headers[header]);
                }
                using (var reader = new System.IO.StreamReader(req.InputStream, req.ContentEncoding))
                {
                    string body = reader.ReadToEnd();
                    Console.WriteLine("\nBody:");
                    Console.WriteLine(body);
                }
                
                // Return dummy response
                var resp = context.Response;
                resp.StatusCode = 200;
                resp.ContentType = "application/json";
                byte[] buf = System.Text.Encoding.UTF8.GetBytes("{\"Id\": 123, \"BaseEntity\": {\"Id\": 123}}");
                resp.ContentLength64 = buf.Length;
                resp.OutputStream.Write(buf, 0, buf.Length);
                resp.Close();
            }
            catch (Exception ex)
            {
                Console.WriteLine("Listener error: " + ex.Message);
            }
            finally
            {
                listener.Close();
            }
        });
        thread.Start();
        
        Thread.Sleep(500); // Wait for listener to start
        
        try
        {
            ServiceManager manager = new ServiceManager("http://localhost:9999/", "apiUser", string.Empty, "fyrqc7c3i7");
            var customFieldData = new CustomFieldData
            {
                CustomFieldId = 1082,
                Data = "PYLMIG-1062",
                IssueId = 418609,
                ProjectId = 81,
                UserId = 5031
            };
            manager.Item.CustomFieldDataUpdate(customFieldData);
        }
        catch (Exception ex)
        {
            Console.WriteLine("SDK Request error: " + ex.Message);
        }
        
        thread.Join();
    }
}
