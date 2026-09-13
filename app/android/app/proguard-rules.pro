# Reglas de ofuscacion para el paquete de release.
#
# Flutter aporta las suyas; estas cubren lo que usa Atenea por encima.

# El motor de Flutter y sus plugins se referencian por reflexion.
-keep class io.flutter.** { *; }
-keep class io.flutter.plugins.** { *; }

# `flutter_secure_storage` usa el proveedor de criptografia de AndroidX.
-keep class androidx.security.crypto.** { *; }

# Las trazas de fallos sin nombres de archivo ni lineas no sirven para nada.
-keepattributes SourceFile,LineNumberTable
-renamesourcefileattribute SourceFile

# Flutter referencia Play Core para los "deferred components" (descargar partes
# de la app a demanda). Atenea no usa esa funcion, asi que esas clases no estan
# en el paquete y R8 se detiene al no encontrarlas. Silenciarlas es lo correcto:
# el codigo que las llama nunca se ejecuta.
-dontwarn com.google.android.play.core.**
-dontwarn com.google.android.play.core.splitcompat.**
-dontwarn com.google.android.play.core.splitinstall.**
-dontwarn com.google.android.play.core.tasks.**
