import java.util.Properties

plugins {
    id("com.android.application")
    id("kotlin-android")
    // The Flutter Gradle Plugin must be applied after the Android and Kotlin Gradle plugins.
    id("dev.flutter.flutter-gradle-plugin")
}

// Credenciales de firma, leidas de `android/key.properties`.
//
// Ese archivo NO esta en el repositorio y no debe estarlo: contiene la
// contrasena del almacen de claves con el que se firma Atenea. Perderlo o
// filtrarlo son las dos unicas formas de no poder volver a publicar una
// actualizacion, asi que vive fuera, junto a una copia de seguridad.
//
// Sin el, la compilacion de release sigue funcionando con la clave de
// depuracion (util para probar `flutter run --release`), pero Play rechaza ese
// paquete. La condicion se comprueba abajo, en `buildTypes`.
val propiedadesDeFirma = Properties().apply {
    val archivo = rootProject.file("key.properties")
    if (archivo.exists()) archivo.inputStream().use { load(it) }
}
val hayFirmaPropia = propiedadesDeFirma.getProperty("storeFile") != null

android {
    namespace = "cl.atenea.atenea"
    compileSdk = flutter.compileSdkVersion
    ndkVersion = flutter.ndkVersion

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    kotlinOptions {
        jvmTarget = JavaVersion.VERSION_17.toString()
    }

    defaultConfig {
        applicationId = "cl.atenea.atenea"
        minSdk = flutter.minSdkVersion
        targetSdk = flutter.targetSdkVersion
        versionCode = flutter.versionCode
        versionName = flutter.versionName
    }

    signingConfigs {
        if (hayFirmaPropia) {
            create("release") {
                storeFile = file(propiedadesDeFirma.getProperty("storeFile"))
                storePassword = propiedadesDeFirma.getProperty("storePassword")
                keyAlias = propiedadesDeFirma.getProperty("keyAlias")
                keyPassword = propiedadesDeFirma.getProperty("keyPassword")
            }
        }
    }

    buildTypes {
        release {
            // Con `key.properties` se firma de verdad; sin el se usa la clave de
            // depuracion para que `flutter run --release` siga funcionando en
            // local. Play rechaza lo segundo, y por eso se avisa al compilar en
            // vez de descubrirlo al subir el paquete.
            signingConfig = if (hayFirmaPropia) {
                signingConfigs.getByName("release")
            } else {
                logger.warn(
                    "Atenea: no hay android/key.properties, asi que este release " +
                        "va firmado con la clave de depuracion. Sirve para probar " +
                        "en local; Play lo rechaza. Ver android/key.properties.ejemplo."
                )
                signingConfigs.getByName("debug")
            }
            isMinifyEnabled = true
            isShrinkResources = true
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro",
            )
        }
    }
}

flutter {
    source = "../.."
}
